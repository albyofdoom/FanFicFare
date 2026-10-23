"""Offline tests for the cli.py update gate and its post-fetch no-change skip.

Drives the real cli.do_download() against the staged adapter from
tests/adapters/update_harness.py, so nothing touches the network.  This
path has no other coverage: the equivalent skip in calibre-plugin/jobs.py
is only reached through Calibre.

Imports fanficfare.cli only, never fanficfare.updategate, so this file
can also be dropped onto a tree without the gate fix to confirm it
actually detects the bug instead of passing vacuously.
"""
import argparse
import io
import os

import pytest

from fanficfare import cli
from fanficfare.configurable import Configuration
from fanficfare.epubutils import get_dcsource_chaptercount, get_update_data
from fanficfare.writers.writer_epub import EpubWriter

from tests.adapters.update_harness import (CH, STORY_URL, StagedSiteAdapter,
                                           chapters_for, staged_download,
                                           strip_chapter_data_meta)

DEFAULTS_INI = os.path.join(os.path.dirname(cli.__file__), 'defaults.ini')

PERSONAL_PRESERVE_ON = (
    '[defaults]\n'
    'update_preserve_deleted_chapters:true\n'
    'update_check_recent_chapters:0\n'
    'include_images:false\n')

PERSONAL_PRESERVE_OFF = PERSONAL_PRESERVE_ON.replace(
    'update_preserve_deleted_chapters:true',
    'update_preserve_deleted_chapters:false')

CHAPTER_BODY = '<p>chapter %d body</p>'

ALL_CHAPTERS = [1, 2, 3, 4, 5]


def make_options(**overrides):
    opts = dict(
        update=True,
        updatealways=False,
        force=False,
        metaonly=False,
        unnew=False,
        normalize=False,
        list=False,
        downloadlist=None,
        nooutput=False,
        format='epub',
        interactive=False,
        jsonmeta=False,
        jsonmetafile=None,
        nometachapters=False,
        updatecover=False,
        save_cache=False,
        progressbar=False,
        mozillacookies=None,
        begin=None,
        end=None,
        configfile=None,
        options=None,
    )
    opts.update(overrides)
    return argparse.Namespace(**opts)


def build_config(personal):
    """Config matching what do_download() will build from the same personal.ini."""
    configuration = Configuration(['example.com'], 'EPUB', lightweight=True)
    configuration.read(DEFAULTS_INI)
    configuration.read_file(io.StringIO(personal))
    return configuration


def run_update(monkeypatch, capsys, tmp_path, epub_chapters, site_chapters,
               personal=PERSONAL_PRESERVE_ON, epub_bytes=None, **options):
    """Update an epub holding epub_chapters against a site serving
    site_chapters.  Returns (adapter, write_calls, warned)."""
    epub = tmp_path / 'story.epub'
    epub.write_bytes(epub_bytes if epub_bytes is not None else staged_download(
        build_config(PERSONAL_PRESERVE_ON),
        {n: CHAPTER_BODY % n for n in epub_chapters}))

    site = {n: CHAPTER_BODY % n for n in site_chapters}
    adapter = StagedSiteAdapter(build_config(personal), STORY_URL)
    adapter.site_chapters = chapters_for(site)
    adapter.content = {CH % n: html for n, html in site.items()}

    # The staged adapter isn't a registered site, so answer the two lookups
    # cli.do_download() does instead of adding it to the adapter registry.
    monkeypatch.setattr(cli.adapters, 'getConfigSectionsFor',
                        lambda url: ['example.com'])
    monkeypatch.setattr(cli.adapters, 'getAdapter',
                        lambda config, url: adapter)
    monkeypatch.setattr(cli, 'call', lambda *args, **kwargs: 0)

    write_calls = []

    def fake_write_story(config, adapter, writeformat, metaonly=False,
                         nooutput=False, outstream=None):
        write_calls.append(writeformat)
        return str(epub)

    monkeypatch.setattr(cli, 'write_story', fake_write_story)

    warned = []
    cli.do_download(str(epub), make_options(**options),
                    open(DEFAULTS_INI).read(), personal,
                    warn=warned.append, fail=warned.append)
    output = capsys.readouterr().out
    return adapter, write_calls, warned, output


def test_unchanged_story_with_preserve_skips_rewrite(monkeypatch, capsys,
                                                     tmp_path):
    """With preserve on, the counts alone can no longer prove 'nothing to
    do', so the update has to fetch first -- but it must still not
    rewrite the book."""
    adapter, write_calls, warned, output = run_update(
        monkeypatch, capsys, tmp_path, ALL_CHAPTERS, ALL_CHAPTERS)

    assert adapter.storyDone is True, 'the update has to fetch to decide'
    assert adapter.story.chapter_error_count == 0
    assert write_calls == []
    assert 'already contains 5 chapters.' in output
    assert warned == []


def test_preserved_deletions_only_skips_rewrite(monkeypatch, capsys, tmp_path):
    """Site lost two chapters, gained none: nothing changed, so no rewrite."""
    adapter, write_calls, warned, output = run_update(
        monkeypatch, capsys, tmp_path, ALL_CHAPTERS, [1, 2, 5])

    assert adapter.story.chapter_written_count == 5
    assert write_calls == []
    assert 'already contains 5 chapters, site only has 3.' in output
    assert warned == []


def test_equal_count_swap_with_preserve_writes(monkeypatch, capsys, tmp_path):
    """The case the gate fix exists for: 1 chapter deleted, 1 added, so
    epub and site both have 5.  Preserve on -> the update must proceed,
    fetch, and write the book with the deleted chapter kept."""
    adapter, write_calls, warned, output = run_update(
        monkeypatch, capsys, tmp_path, ALL_CHAPTERS, [1, 2, 3, 4, 6])

    assert adapter.story.chapter_added_count == 1
    assert adapter.story.chapter_written_count == 6
    assert [ch['url'] for ch in adapter.story.chapters] == \
        [CH % n for n in [1, 2, 3, 4, 5, 6]]
    assert write_calls == ['epub']
    assert 'Do update - epub(5) vs url(5)' in output


def test_equal_count_swap_without_preserve_skips(monkeypatch, capsys,
                                                 tmp_path):
    """Same counts, preserve off: no way to tell a swap from 'nothing to
    do', so the pre-existing count-based skip still applies and the
    update must not fetch or write."""
    adapter, write_calls, warned, output = run_update(
        monkeypatch, capsys, tmp_path, ALL_CHAPTERS, [1, 2, 3, 4, 6],
        personal=PERSONAL_PRESERVE_OFF)

    assert adapter.storyDone is False
    assert write_calls == []
    assert 'already contains 5 chapters.' in output
    assert warned == []


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('try_limit', [1, 5])
@pytest.mark.parametrize('personal', [PERSONAL_PRESERVE_OFF, PERSONAL_PRESERVE_ON],
                         ids=['preserve-off', 'preserve-on'])
def test_update_retries_error_chapters(monkeypatch, capsys, tmp_path,
                                      legacy, try_limit, personal):
    """Failed and unattempted chapters must not block an ordinary update."""
    configuration = build_config(
        personal + 'continue_on_chapter_error:true\n'
        'continue_on_chapter_error_try_limit:%d\n' % try_limit)
    initial = StagedSiteAdapter(configuration, STORY_URL)
    initial.site_chapters = chapters_for({n: '' for n in ALL_CHAPTERS})
    # The missing second chapter raises a download error.  With limit=1,
    # subsequent chapters become error placeholders without being fetched.
    initial.content = {CH % n: CHAPTER_BODY % n for n in [1, 3, 4, 5]}
    initial.getStory()
    failed = [2, 3, 4, 5] if try_limit == 1 else [2]
    assert initial.story.chapter_error_count == len(failed)
    out = io.BytesIO()
    EpubWriter(configuration, initial).writeStory(outstream=out)
    epub_bytes = out.getvalue()
    if legacy:
        epub_bytes = strip_chapter_data_meta(epub_bytes)

    fetched = []
    original_fetch = StagedSiteAdapter.getChapterTextNum

    def track_fetch(self, url, index):
        fetched.append(url)
        return original_fetch(self, url, index)

    monkeypatch.setattr(StagedSiteAdapter, 'getChapterTextNum', track_fetch)
    adapter, write_calls, warned, output = run_update(
        monkeypatch, capsys, tmp_path, ALL_CHAPTERS, ALL_CHAPTERS,
        personal=personal, epub_bytes=epub_bytes)

    assert adapter.storyDone is True
    assert fetched == [CH % n for n in failed]
    assert adapter.story.chapter_error_count == 0
    assert write_calls == ['epub']
    assert warned == []
    assert 'already contains' not in output

    # Verify both readers used by CLI and Calibre exclude the placeholders
    # from their counts and reusable chapter bodies/metadata.
    expected_good_urls = {CH % n for n in ALL_CHAPTERS if n not in failed}
    data = get_update_data(io.BytesIO(epub_bytes))
    assert get_dcsource_chaptercount(io.BytesIO(epub_bytes)) == \
        (STORY_URL, len(expected_good_urls))
    assert data[1] == len(data[2]) == len(expected_good_urls)
    assert set(data[7]) == set(data[8]) == expected_good_urls

    repaired = io.BytesIO()
    EpubWriter(adapter.configuration, adapter).writeStory(outstream=repaired)
    repaired_data = get_update_data(io.BytesIO(repaired.getvalue()))
    assert repaired_data[1] == 5
    assert list(repaired_data[7]) == [CH % n for n in ALL_CHAPTERS]
    assert all('(CHAPTER ERROR)' not in chapter['title']
               for chapter in repaired_data[8].values())
    for n, soup in enumerate(repaired_data[2], 1):
        assert CHAPTER_BODY % n in str(soup)
