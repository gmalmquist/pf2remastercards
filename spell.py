#!/usr/bin/env python3
import datetime
import json
import os
import re
import sys

from http.server import BaseHTTPRequestHandler, HTTPServer
from io import StringIO
from subprocess import check_output, Popen, PIPE, STDOUT

class SpellCache:
  spells = {}
  retention = datetime.timedelta(days = 1)

  @classmethod
  def put(cls, name, spell):
    cls.spells[name] = (spell, datetime.datetime.now())

  @classmethod
  def get(cls, name):
    spell, time = cls.spells.get(name, (None, None))
    if spell is None:
      return None
    if time + cls.retention < datetime.datetime.now():
      return None
    return spell

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
  spell = SpellCache.get(spell_name)
  if spell is not None:
    return spell
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
      spell = AttrDict(hits[0].get('_source'))
      SpellCache.put(spell_name, spell)
      return spell


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
    rank = spell.level if spell.spell_type != 'Cantrip' else '',
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

def write_cards(cards, out):
  with open('head.html', 'rb') as f:
    out.write(f.read())

  spells = filter(None, map(search_spell, cards))
  spells = sorted(spells, key = lambda s: (s.spell_type, s.level, s.name))
  for spell in spells:
    out.write(format_card(spell).encode('utf8'))

  with open('tail.html', 'rb') as f:
    out.write(f.read())

class RequestHandler(BaseHTTPRequestHandler):
  VALID_PATH = re.compile(r'^[a-zA-Z0-9]+([.][a-zA-Z0-9]+)?$')
  R404 = '''
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <title>404</title>
    </head>
    <body>
      <h1>404 Not Found</h1>
    </body>
    </html>
  '''.strip().encode('utf8')
  CONTENT_TYPES = {
    'css': 'text/css',
    'js': 'text/javascript',
    'json': 'application/json',
    'html': 'text/html',
    'png': 'image/x-png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'ico': 'image/x-icon',
  }

  def _send(self, content, code = 200, mime = 'text/html'):
    self.send_response(code)
    self.send_header('Content-Type', mime)
    self.send_header('Access-Control-Allow-Origin: https://gmalmquist.github.io', mime)
    self.send_header('Access-Control-Allow-Origin: https://gwenscode.com', mime)
    self.send_header('Content-Length', len(content))
    self.end_headers()
    self.wfile.write(content)
    self.wfile.flush()

  def do_OPTIONS(self):
    self.send_response(200)
    self.send_header('Access-Control-Allow-Origin: https://gmalmquist.github.io', mime)
    self.send_header('Access-Control-Allow-Origin: https://gwenscode.com', mime)
    self.end_headers()

  def do_HEAD(self):
    self.send_response(200)
    self.send_header('Access-Control-Allow-Origin: https://gmalmquist.github.io', mime)
    self.send_header('Access-Control-Allow-Origin: https://gwenscode.com', mime)
    self.end_headers()

  def do_GET(self):
    path = self.path.lstrip('/').lstrip('?').strip()
    if path == '':
      path = 'index.html'
    filepath = os.path.normpath(os.path.join(os.getcwd(), path))

    if RequestHandler.VALID_PATH.match(path) is None:
      self._send("Invalid path. Don't be sneaky.".encode('utf8'), code = 400)
      return

    if not os.path.exists(filepath):
      self._send(RequestHandler.R404, code = 404)
      return

    extension = path[path.rfind('.')+1:] if '.' in path else ''
    with open(filepath, 'rb') as f:
      self._send(
        f.read(),
        code = 200,
        mime = RequestHandler.CONTENT_TYPES.get(extension.lower(), 'text/html'),
      )
      return

  def do_POST(self):
    try:
      content_length = int(self.headers['Content-Length'])
      data = json.loads(self.rfile.read(content_length).decode('utf8'))
    except Exception as e:
      self._send('Invalid data: {}'.format(str(e)).encode('utf8'), code = 400)
      return
    self.send_response(200)
    self.send_header('Content-Type', 'text/html')
    self.end_headers()
    write_cards(data, self.wfile)
    return

if len(sys.argv) <= 1:
  addr = ('', 8120)
  httpd = HTTPServer(addr, RequestHandler)
  httpd.serve_forever()
else:
  write_cards(sys.argv[1:], sys.stdout)
  sys.stdout.flush()

