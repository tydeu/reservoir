#!/usr/bin/env python3
import argparse
import subprocess
import requests
import json
import logging

def query(num):
  query = "language:Lean stars:>1 sort:stars"
  fields = ["fullName","description","updatedAt","url"]
  child = subprocess.run([
    "gh", "search", "repos",
    *query.split(' '), "-L", str(num), "--json", ','.join(fields),
  ], stdout=subprocess.PIPE)
  return json.loads(child.stdout)

def filter_lake(repo):
  repo = repo['fullName']
  url = f"https://raw.githubusercontent.com/{repo}/HEAD/lakefile.lean"
  logging.info(f"querying {url}")
  code = requests.head(url).status_code
  log = f"status {code} for repository {repo}"
  if code == 404:
    logging.debug(log)
    return False
  elif code == 200:
    logging.debug(log)
    return True
  else:
    logging.error(f"status {code} for repository {repo}")
    return False

def gen_id(repo):
  repo['id'] = repo['fullName'].replace("-", "--").replace("/", "-")
  return repo

if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument('num', type=int,
    help='max number of results to curate')
  parser.add_argument('-Q', '--query', type=int, default=None,
    help='(max) number of results to query from GitHub')
  parser.add_argument('-X', '--exclusions', default="exclusions.txt",
    help='file containing repos to exclude')
  parser.add_argument('-o', '--output',
    help='file to output results')
  parser.add_argument('-q', '--quiet', dest="verbosity", action='store_const', const=0, default=1,
    help='print no logging information')
  parser.add_argument('-v', '--verbose', dest="verbosity", action='store_const', const=2,
    help='print verbose logging information')
  args = parser.parse_args()

  if args.verbosity == 0:
    level = logging.CRITICAL
  elif args.verbosity == 1:
    level = logging.INFO
  else:
    level = logging.DEBUG
  logging.basicConfig(level=level, format='%(levelname)s: %(message)s')

  exclusions = set()
  with open(args.exclusions, 'r') as f:
    for line in f: exclusions.add(line.strip())

  num_query = args.query
  if num_query is None:
    num_query = args.num * 5

  repos = query(num_query)
  logging.info(f"found {len(repos)} (max {num_query}) notable Lean repositories")
  repos = filter(lambda repo: repo['fullName'] not in exclusions, repos)
  repos = filter(filter_lake, repos)
  repos = map(gen_id, repos)
  repos = list(repos)
  logging.info(f"found {len(repos)} notable Lean repositories with lakefiles (picking {args.num})")
  repos = repos[0:args.num]

  if args.output is None:
    print(json.dumps(repos))
  else:
    with open(args.output, 'w') as f:
      f.write(json.dumps(repos))





