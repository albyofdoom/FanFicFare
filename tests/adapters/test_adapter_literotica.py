"""Offline metadata and chapter regressions using minimal Solid hydration pages."""
from io import BytesIO
import json
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile

import pytest

from fanficfare.adapters.adapter_literotica import LiteroticaSiteAdapter
from fanficfare.configurable import Configuration, get_valid_set_options
from fanficfare import adapters, cli, configurable, writers


ROOT = Path(__file__).resolve().parents[2]
SINGLE_URL = 'https://www.literotica.com/s/example-story'
SERIES_URL = 'https://www.literotica.com/series/se/12345'
DEFAULTS = ['fanficfare/defaults.ini', 'calibre-plugin/plugin-defaults.ini']


def hydration(kind, fields):
    return (r'_$HY.r["%s[\"example\"]"]=$R[0]=($R[1]={});'
            r'$R[0]($R[1],$R[2]={%s});_$HY.r["end"]=0;' % (kind, fields))


def page(series=False, fields='userid:42,', intro=None, meta='A &lt;special&gt; story.',
         descriptions=('First &lt;part&gt;.', 'Second part.'), category_link=True,
         chapter_fields=None, author_url='https://www.literotica.com/authors/Example/works/stories'):
    html = '<h1>Example Story</h1><div class="_sidebar_test"></div>'
    html += '<a class="_author__title_test" href="%s">Example</a>' % author_url
    if meta is not None:
        html += '<meta name="description" content="%s">' % meta
    if intro is not None:
        html += '<div class="_introduction-wrap_test">%s</div>' % intro
    if series:
        html += '<section><ul class="_list_test">'
        for i, description in enumerate(descriptions):
            html += ('<li class="_item_test"><a href="%s-%d">Part %d</a>'
                     '<p class="_description_test">%s%s</p></li>' % (
                         SINGLE_URL, i + 1, i + 1, description,
                         '<a href="/c/romance">Romance</a>' if category_link else ''))
        html += '</ul></section>'
        html += '<script>' + hydration('seriesInfo', 'id:12345,state:"completed",' + fields)
        if chapter_fields is None:
            chapter_fields = ('view_count:10,favorite_count:2,rate_count:3,',
                              'view_count:20,favorite_count:4,rate_count:5,')
        works = ','.join('$R[%d]={id:%d,%s}' % (i + 12, i + 1, values)
                         for i, values in enumerate(chapter_fields))
        html += (r'_$HY.r["seriesWorks[\"example\"]"]=$R[10]=($R[11]=[]);'
                 r'$R[10]($R[11],[%s]);' % works)
    else:
        html += '<nav class="_breadcrumbs_test"><a>Home</a><a>Romance</a></nav>'
        html += '<script>' + hydration('workData', 'id:1,' + fields)
    # Unrelated counts and user IDs must never override or enter the totals.
    html += 'recommendations={userid:999,view_count:999,favorite_count:999,rate_count:999};</script>'
    html += '<div class="_article__content_test"><div><p>Chapter body.</p></div></div>'
    return html


def adapter_for(html, series=False, defaults=DEFAULTS[0], **options):
    config = Configuration(['literotica.com'], 'epub', lightweight=True)
    config.read(str(ROOT / defaults))
    config.set('literotica.com', 'is_adult', 'true')
    config.set('literotica.com', 'include_images', 'false')
    for key, value in options.items():
        config.set('literotica.com', key, str(value).lower())
    url = SERIES_URL if series else SINGLE_URL
    adapter = LiteroticaSiteAdapter(config, url)
    adapter.get_request_redirected = Mock(return_value=(html, url))
    adapter.get_request = Mock(return_value=html)
    return adapter


@pytest.mark.parametrize('defaults', DEFAULTS)
@pytest.mark.parametrize('series', [False, True])
def test_defaults_and_opt_in_metadata(defaults, series):
    html = page(series=series, fields='userid:42,view_count:7,favorite_count:0,rate_count:2,')
    adapter = adapter_for(html, series, defaults)
    adapter.extractChapterUrlsAndMetadata()
    assert adapter.story.getMetadata('authorId') == 'Example'
    for key in ('views', 'favorites', 'votes'):
        assert adapter.story.getMetadataRaw(key) is None
    adapter = adapter_for(html, series, defaults,
                          use_numeric_author_id=True, collect_story_statistics=True)
    adapter.extractChapterUrlsAndMetadata()
    assert adapter.story.getMetadata('authorId') == '42'
    assert adapter.story.getMetadata('views') == ('30' if series else '7')
    assert adapter.story.getMetadata('favorites') == ('6' if series else '0')
    assert adapter.story.getMetadata('votes') == ('8' if series else '2')
    assert adapter.num_chapters() == (2 if series else 1)
    adapter.get_request_redirected.assert_called_once()
    adapter.get_request.assert_not_called()


@pytest.mark.parametrize('fields,expected', [
    ('"userid": "42",', '42'), ('user_id:42,', '42'),
    ('userid:42,user_id:42,', '42'), ('userid:42,user_id:43,', 'Example'),
    ('userid:null,', 'Example'), ('other_userid:99,', 'Example'),
])
def test_numeric_author_id_fallback(fields, expected):
    adapter = adapter_for(page(fields=fields), use_numeric_author_id=True)
    adapter.extractChapterUrlsAndMetadata()
    assert adapter.story.getMetadata('authorId') == expected


@pytest.mark.parametrize('numeric', [False, True])
def test_legacy_author_uid(numeric):
    adapter = adapter_for(page(author_url='https://www.literotica.com/stories/memberpage.php?uid=123&amp;page=submissions'),
                          use_numeric_author_id=numeric)
    adapter.extractChapterUrlsAndMetadata()
    assert adapter.story.getMetadata('authorId') == '123'


def test_author_url_query_without_uid():
    adapter = adapter_for(page(author_url='https://www.literotica.com/authors/Example/works?sort=date'))
    adapter.extractChapterUrlsAndMetadata()
    assert adapter.story.getMetadata('authorId') == 'Example'


@pytest.mark.parametrize('fields', [
    'view_count:null,', 'view_count:-1,', 'view_count:1.5,', 'total_view_count:99,',
    'view_count:1,view_count:2,', '',
])
def test_missing_or_ambiguous_statistics_are_omitted(fields):
    adapter = adapter_for(page(fields=fields), collect_story_statistics=True)
    adapter.extractChapterUrlsAndMetadata()
    assert adapter.story.getMetadataRaw('views') is None


def test_quoted_statistics_and_plural_favorites():
    adapter = adapter_for(page(fields='"view_count":"10","favorites_count":0,"rate_count":2,'),
                          collect_story_statistics=True)
    adapter.extractChapterUrlsAndMetadata()
    assert adapter.story.getMetadata('views') == '10'
    assert adapter.story.getMetadata('favorites') == '0'
    assert adapter.story.getMetadata('votes') == '2'


def test_series_count_at_end_of_hydration_resource():
    adapter = adapter_for(page(series=True, chapter_fields=('view_count:10', 'view_count:20')),
                          series=True, collect_story_statistics=True)
    adapter.extractChapterUrlsAndMetadata()
    assert adapter.story.getMetadata('views') == '30'


def test_incomplete_series_statistics_do_not_use_series_or_recommendation_counts():
    adapter = adapter_for(page(series=True, fields='view_count:400,', chapter_fields=(
        'view_count:10,favorite_count:0,rate_count:3,',
        'view_count:null,favorite_count:1,rate_count:5,')),
        series=True, collect_story_statistics=True)
    adapter.extractChapterUrlsAndMetadata()
    assert adapter.story.getMetadataRaw('views') is None
    assert adapter.story.getMetadata('favorites') == '1'
    assert adapter.story.getMetadata('votes') == '8'


@pytest.mark.parametrize('include_chapters', [False, True])
def test_series_and_individual_descriptions(include_chapters):
    adapter = adapter_for(page(series=True, intro='<p>Series introduction.</p><p>More detail.</p>'),
                          series=True, include_chapter_descriptions_in_summary=include_chapters)
    adapter.extractChapterUrlsAndMetadata()
    desc = adapter.story.getMetadata('description')
    assert desc.count('Series introduction.') == 1
    assert 'More detail.' in desc
    assert ('1. First &lt;part&gt;.' in desc) == include_chapters
    assert ('2. Second part.' in desc) == include_chapters
    assert adapter.story.getMetadata('category') == 'Romance'


@pytest.mark.parametrize('intro', [None, '<p>Series "Example" has 2 chapters.</p>',
                                  '<p>Series “Example” has 2 chapters.</p>'])
@pytest.mark.parametrize('category_link', [False, True])
def test_series_description_fallback(intro, category_link):
    adapter = adapter_for(page(series=True, intro=intro, category_link=category_link), series=True)
    adapter.extractChapterUrlsAndMetadata()
    desc = adapter.story.getMetadata('description')
    assert '1. First &lt;part&gt;.' in desc
    assert '2. Second part.' in desc
    assert 'has 2 chapters' not in desc


def test_real_description_starting_like_generated_text_is_preserved():
    intro = '<p>Series "Example" has 2 chapters. This is an introduction.</p>'
    adapter = adapter_for(page(series=True, intro=intro), series=True)
    adapter.extractChapterUrlsAndMetadata()
    assert 'This is an introduction.' in adapter.story.getMetadata('description')


@pytest.mark.parametrize('meta', ['A &lt;special&gt; story.', None])
def test_single_story_description(meta):
    adapter = adapter_for(page(meta=meta))
    adapter.extractChapterUrlsAndMetadata()
    desc = adapter.story.getMetadata('description')
    if meta:
        assert 'A &lt;special&gt; story.' in desc
    else:
        assert not desc


def test_single_info_description_takes_precedence_over_meta():
    html = page().replace('<h1>', '<div id="tabpanel-info"><div class="bn_B">Info summary.</div></div><h1>')
    adapter = adapter_for(html, include_chapter_descriptions_in_summary=True)
    adapter.extractChapterUrlsAndMetadata()
    desc = adapter.story.getMetadata('description')
    assert desc.count('Info summary.') == 1
    assert 'special' not in desc


def test_single_story_text_wrapper_is_not_a_series_introduction():
    # The live single-story DOM reuses the series introduction class.
    html = page().replace('<p>Chapter body.</p>',
                          '<div class="_introduction-wrap_test"><p>Chapter body.</p></div>')
    adapter = adapter_for(html)
    adapter.extractChapterUrlsAndMetadata()
    desc = adapter.story.getMetadata('description')
    assert 'A &lt;special&gt; story.' in desc
    assert 'Chapter body.' not in desc
    assert 'Chapter body.' in adapter.getChapterText(SINGLE_URL)


def test_legacy_chapter_description_selector():
    html = page(series=True).replace('class="_description_test"', 'class="br_rk"')
    adapter = adapter_for(html, series=True)
    adapter.extractChapterUrlsAndMetadata()
    assert '1. First &lt;part&gt;.' in adapter.story.getMetadata('description')


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('meta', ['A &lt;special&gt; story.', None])
def test_chapter_description(enabled, meta):
    adapter = adapter_for(page(meta=meta), description_in_chapter=enabled)
    text = adapter.getChapterText(SINGLE_URL)
    assert 'Chapter body.' in text
    assert ('<b>Description:</b>' in text) == (enabled and meta is not None)
    if enabled and meta:
        assert 'A &lt;special&gt; story.' in text


@pytest.mark.parametrize('defaults', DEFAULTS)
def test_options_registered_and_defaults_sections_match(monkeypatch, defaults):
    adapter = adapter_for(page(), defaults=defaults)
    # Existing circular imports can leave this binding unset during collection.
    monkeypatch.setattr(configurable, 'adapters', adapters, raising=False)
    options = get_valid_set_options()
    for key in ('use_numeric_author_id', 'collect_story_statistics'):
        assert options[key][0] == ['literotica.com']
        assert options[key][2] == ['true', 'false']
        assert not adapter.getConfig(key)
    configs = []
    for filename in DEFAULTS:
        config = Configuration(['literotica.com'], 'epub', lightweight=True)
        config.read(str(ROOT / filename))
        configs.append(dict(config.items('literotica.com')))
    assert configs[0] == configs[1]


@pytest.mark.parametrize('defaults', DEFAULTS)
def test_cli_metadata_uses_literotica_options(monkeypatch, capsys, defaults):
    html = page(fields='userid:42,view_count:7,favorite_count:0,rate_count:2,')
    monkeypatch.setattr(LiteroticaSiteAdapter, 'get_request_redirected',
                        lambda self, url: (html, url))
    # Isolate the CLI from personal files; defaults/personal.ini are passed below.
    monkeypatch.setattr(Configuration, 'read', lambda self, filenames: [])
    personal = ('[overrides]\nis_adult:true\ninclude_images:false\n'
                'use_numeric_author_id:true\ncollect_story_statistics:true\n')
    cli.main(['--meta-only', '--json-meta', '--no-output', '--non-interactive', SINGLE_URL],
             passed_defaultsini=(ROOT / defaults).read_text(encoding='utf8'),
             passed_personalini=personal)
    output = capsys.readouterr().out
    assert output.lstrip().startswith('{'), output
    metadata = json.loads(output)
    assert metadata['authorId'] == '42'
    assert metadata['views'] == '7'
    assert metadata['favorites'] == '0'
    assert 'special' in metadata['description']


@pytest.mark.parametrize('defaults', DEFAULTS)
def test_epub_contains_statistics_and_both_descriptions(defaults):
    adapter = adapter_for(page(series=True, intro='<p>Series introduction.</p>'),
                          series=True, defaults=defaults, use_numeric_author_id=True,
                          collect_story_statistics=True, description_in_chapter=True,
                          include_chapter_descriptions_in_summary=True)
    adapter.get_request.side_effect = lambda url, **kwargs: page()
    stream = BytesIO()
    writers.getWriter('epub', adapter.configuration, adapter).writeStory(outstream=stream)
    with ZipFile(stream) as epub:
        title = epub.read('OEBPS/title_page.xhtml').decode('utf8')
        assert 'Views' in title and '30' in title
        assert 'Favorites' in title and '6' in title
        assert 'Votes' in title and '8' in title
        assert title.count('Series introduction.') == 1
        assert 'First &lt;part&gt;.' in title
        for filename in ('OEBPS/file0001.xhtml', 'OEBPS/file0002.xhtml'):
            chapter = epub.read(filename).decode('utf8')
            assert chapter.count('<b>Description:</b>') == 1
            assert 'A &lt;special&gt; story.' in chapter
            assert 'Chapter body.' in chapter
