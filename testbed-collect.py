#!/usr/bin/env python3
from utils import *
from typing import TypedDict
from datetime import datetime
import logging
import json
import re
import argparse
import os

class Job(TypedDict):
  id: int
  name: str

TESTBED_REPO = "leanprover/reservoir"
def query_jobs(run_id: int, run_attempt: int = 1) -> 'list[Job]':
  out = capture_cmd(
    'gh', 'api', '--paginate',
    f"repos/{TESTBED_REPO}/actions/runs/{run_id}/attempts/{run_attempt}/jobs",
    '-q', '.jobs[] | {id,name}'
  )
  return list(map(json.loads, out.splitlines()))

BUILD_RE = re.compile("Build (.*)")
def is_build_job(job: Job, name: str):
  match = BUILD_RE.search(job['name'])
  return match is not None and match.group(1) == name

if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument('results',
    help="directory containing testbed results")
  parser.add_argument('run_id', type=int,
    help="the testbed run ID")
  parser.add_argument('run_attempt', nargs='?', type=int, default=1,
    help="the testbed run attempt")
  parser.add_argument('-m', '--matrix',
    help="file containing the JSON build matrix")
  parser.add_argument('-D', '--index-dir', default=None,
    help='directory to output hierarchical index')
  parser.add_argument('-o', '--output',
    help='file to output the bundle manifest')
  parser.add_argument('-q', '--quiet', dest="verbosity", action='store_const', const=0, default=1,
    help='print no logging information')
  parser.add_argument('-v', '--verbose', dest="verbosity", action='store_const', const=2,
    help='print verbose logging information')
  args = parser.parse_args()

  configure_logging(args.verbosity)

  matrix_file = args.matrix
  if matrix_file is None:
    matrix_file = os.path.join(args.results, 'matrix', 'matrix.json')

  with open(matrix_file, 'r') as f:
    matrix = json.load(f)

  jobs = query_jobs(args.run_id, args.run_attempt)
  def find_build_job(name: str) -> Job:
    return next(job for job in jobs if is_build_job(job, name))

  results: 'dict[str, list]'= dict()
  for entry in matrix:
    jobId = find_build_job(entry['buildName'])['id']
    result = {
      'url': f"https://github.com/{TESTBED_REPO}/actions/runs/{args.run_id}/job/{jobId}#step:4:1",
      'builtAt': datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    result_file = os.path.join(args.results, entry['artifact'], 'result.json')
    if not os.path.exists(result_file):
      continue
    with open(result_file, 'r') as f:
      result |= json.load(f)
    if entry['fullName'] not in results:
      results[entry['fullName']] = list()
    results[entry['fullName']].append(result)

  if args.index_dir is not None:
    for (full_name, pkg_results) in results.items():
      pkg_dir = os.path.join(args.index_dir, full_name)
      if not os.path.exists(pkg_dir):
        logging.error(f"{full_name}: build save failed: {pkg_dir} does not exist")
        continue
      builds_file = os.path.join(pkg_dir, 'builds.json')
      if os.path.exists(builds_file):
        with open(os.path.join(pkg_dir, 'builds.json'), 'r') as f:
          builds = json.load(f)
        builds = insert_build_results(builds, pkg_results)
      else:
        builds = pkg_results
      with open(builds_file, 'w') as f:
        f.write(json.dumps(builds, indent=2))
        f.write('\n')

  if args.output is None:
    print(json.dumps(results, indent=2))
  else:
    with open(args.output, 'w') as f:
      f.write(json.dumps(results, indent=2))
