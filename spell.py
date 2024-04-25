#!/usr/bin/env python3
import json
import re
import sys

from subprocess import check_output, Popen, PIPE, STDOUT

class AttrDict:
  def __init__(self, store):
    self._store = store

  def __getattr__(self, name):
    if name.startswith('_'):
      return super(AttrDict, self).__getattr__(name)
    return self[name]

  def __getitem__(self, name):
    return self._store.get(name)

def search_spell(spell_name):
  headers = {
    'Accept-Encoding': 'gzip, deflate, br',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'Content-Type': 'application/json',
    'Origin': ' https://2e.aonprd.com',
    'Connection': ' keep-alive',
    'Referer': ' https://2e.aonprd.com/',
    'Sec-Fetch-Dest': ' empty',
    'Sec-Fetch-Mode': ' cors',
    'Sec-Fetch-Site': ' same-site',
    'TE': ' trailers',
	}
  command = [
		'curl',
    'https://elasticsearch.aonprd.com/aon/_search?track_total_hits=true',
    '-vvv',
    '--compressed',
    '-X',
    'POST',
  ]
  for name, value in headers.items():
    command.extend(['-H', '{}: {}'.format(name, value)])
  command.append('--data-raw')
  command.append(json.dumps({
		"query": {
			"function_score": {
				"query": {
					"bool": {
						"should": [
							{
								"query_string": {
									"query": "{name} type:(spell OR cantrip)".format(name = spell_name),
									"default_operator": "AND",
									"fields": [
										"name",
										"legacy_name",
										"remaster_name",
										"text^0.1",
										"trait_raw",
										"type"
									]
								}
							}
						],
						"filter": [
							{
								"bool": {
									"must_not": {
										"exists": {
											"field": "remaster_id"
										}
									}
								}
							}
						],
						"must_not": [
							{
								"term": {
									"exclude_from_search": True
								}
							}
						],
						"minimum_should_match": 1
					}
				},
				"boost_mode": "multiply",
				"functions": [
					{
						"filter": {
							"terms": {
								"type": [
									"Ancestry",
									"Class"
								]
							}
						},
						"weight": 1.1
					},
					{
						"filter": {
							"terms": {
								"type": [
									"Trait"
								]
							}
						},
						"weight": 1.05
					}
				]
			}
		},
		"size": 50,
		"sort": [
			"_score",
			"_doc"
		],
		"_source": {
			"excludes": [
				"text"
			]
		},
		"aggs": {
			"group1": {
				"composite": {
					"sources": [
						{
							"field1": {
								"terms": {
									"field": "type",
									"missing_bucket": True,
								}
							}
						}
					],
					"size": 10000
				}
			}
		}
	}))
  p = Popen(command, stdout=PIPE, stderr=PIPE)
  out, err = p.communicate()
  if p.returncode != 0:
    raise ValueError(err)
  response = json.loads(out.decode('utf8'))
  if type(response) == type({}):
    hits = response.get('hits', {}).get('hits', [])
    if len(hits) > 0:
      return AttrDict(hits[0].get('_source'))
  sys.stderr.write('Invalid spell: {}\n'.format(json.dumps(response, indent = 2)))
  sys.stderr.flush()

def there(value):
  if value is None:
    return False
  if type(value) == str:
    return len(value.strip()) > 0
  if type(value) == list:
    return any(map(there, value))
  if type(value) == dict:
    return any(map(there, value.values()))
  return True

def format_card(spell):
  def prop(name, label, value):
    if not there(value):
      return ''
    return '''
      <div class="prop">
        <label>{label}</label><span class="{name}">{value}</span>
      </div>
    '''.format(name = name, label = label, value = value)
  def props(name, pairs):
    if not there(pairs):
      return ''
    return '''
      <div class="prop">
        {pairs}
      </div>
    '''.format(name = name, pairs = ''.join([
      '''
        <label>{label}</label><span class="{name}">{value}</span>
      '''.format(name = name, label = key, value = value).strip()
      for key, value in pairs
      if there(value)
    ]))
  def props_list(name, label, values):
    if not there(values):
      return ''
    if type(values) != list:
      values = [values]
    return '''
      <div class="prop">
        {items}
      </div>
    '''.format(name = name, items = ''.join([
      '''
        <span class="{name}">{value}</span>
      '''.format(name = name, value = value).strip()
      for value in values
      if there(value) 
    ]))

  card = ['<div class="card">']
  card.append('''
    <div class="card-head">
      <span class="card-title">{title}</span>
      <span class="card-rank">{spell_type} {rank}</span>
    </div>
    <div class="traits">
      {traits}
    </div>
  '''.format(
    title = spell.name,
    spell_type = spell.spell_type,
    rank = spell.level if spell.spell_type == 'Spell' else '',
    traits = ''.join('<span class="trait">{}</span>'.format(trait) for trait in (spell.trait or [])),
  ))
  card.append(prop('pfs', 'PFS', spell.pfs if spell.pfs != 'Standard' else None))
  card.append(props_list('source', 'Source', spell.source_raw))
  card.append(props_list('tradition', 'Traditions', spell.tradition))
  card.append(props_list('deity', 'Deity', spell.deity))
  card.append(props_list('lesson', 'Lesson', spell.lesson))
  card.append(props_list('patron-theme', 'Patron Theme', spell.patron_theme))
  card.append(prop('actions ' + re.sub(r'[^a-zA-Z0-9]+', '-', spell.actions.strip()).lower(), 'Cast', spell.actions))
  card.append(props('range', [
    ('Range', spell.range),
    ('Area', spell.area),
    ('Targets', spell.target),
  ]))
  card.append(prop('defense', 'Defense', spell.saving_throw))
  card.append(prop('duration', 'Duration', spell.duration_raw))

  body = spell.markdown[spell.markdown.find('---'):].strip()
  body = re.sub(r'[*][*](.*?)[*][*]', r'<strong>\1</strong>', body)
  body = re.sub(r'_([^_\r\n]*?)_', r'<emph>\1</emph>', body)
  body = re.sub(
    r'\[(.*?)\]\((.*?)\)',
    r'<a href="https://2e.aonprd.com\2">\1</a>',
    body,
  )
  body = re.sub(r'[\r\n]{3,}', r'\n<p>\n', body)
  body = re.sub(r'---', r'<hr />', body)
  card.append('<div class="card-body">\n')
  card.append(body)
  card.append('\n</div>')
  card.append('\n</div>')

  return ''.join(card)

with open('head.html', 'r') as f:
  print(f.read())

spells = filter(None, map(search_spell, sys.argv[1:]))
spells = sorted(spells, key = lambda s: (s.spell_type, s.level, s.name))
for spell in spells:
  print(format_card(spell))

with open('tail.html', 'r') as f:
  print(f.read())

