#!/usr/bin/env python3
from utils import *
from typing import TypedDict
import json
import argparse
import os

class Job(TypedDict):
  id: int
  name: str

TESTBED_REPO = "leanprover/reservoir"
def query_jobs(repo: str, run_id: int, run_attempt: int = 1) -> 'list[Job]':
  out = capture_cmd(
    'gh', 'api', '--paginate',
    f"repos/{repo}/actions/runs/{run_id}/attempts/{run_attempt}/jobs",
    '-q', '.jobs[] | {id,name}'
  )
  return list(map(json.loads, out.splitlines()))

def walk_entries(matrix: TestbedMatrix) -> Iterable[TestbedEntry]:
  for layer in matrix:
    yield from layer['data']

def mk_testbed_result(entry: TestbedEntry, pkg_result: PackageResult) -> TestbedResult:
  result = cast(TestbedResult, pkg_result)
  result['repoId'] = entry['repoId']
  result['indexName'] = entry['indexName']
  return result

if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument('results',
    help="directory containing testbed results")
  parser.add_argument('run_id', type=int,
    help="testbed run ID")
  parser.add_argument('run_attempt', nargs='?', type=int, default=1,
    help="testbed run attempt")
  parser.add_argument('-m', '--matrix',
    help="file containing the JSON build matrix")
  parser.add_argument('-o', '--output',
    help='file to output the collected results')
  parser.add_argument('-R', '--repo',
    help='repository with testbed jobs', default=TESTBED_REPO)
  parser.add_argument('-q', '--quiet', dest="verbosity", action='store_const', const=0, default=1,
    help='print no logging information')
  parser.add_argument('-v', '--verbose', dest="verbosity", action='store_const', const=2,
    help='print verbose logging information')
  args = parser.parse_args()

  configure_logging(args.verbosity)

  if not S3_ENABLED:
    logging.warning("No cloud storage configured; will not retain build archives")

  jobs = query_jobs(args.repo, args.run_id, args.run_attempt)
  def find_testbed_job_id(name: str) -> int | None:
    return next((job['id'] for job in jobs if job['name'].split(' / ')[-1] == name), None)

  # Load testbed matrix
  matrix_file = args.matrix
  if matrix_file is None:
    matrix_file = os.path.join(args.results, 'matrix', 'matrix.json')
  with open(matrix_file, 'r') as f:
    matrix: TestbedMatrix = json.load(f)
  entries = list(walk_entries(matrix))
  logging.info(f"Testbed entries: {len(entries)}")

  # Collect results
  num_opt_outs = 0
  num_build_results = 0
  results: TestbedResults = list[TestbedResult]()
  archive_sizes = list[int]()
  for entry in entries:
    jobId = find_testbed_job_id(entry['jobName'])
    if jobId is None:
      logging.error(f"Job ID not found for '{entry['jobName']}'")
      continue
    url = f"https://github.com/{TESTBED_REPO}/actions/runs/{args.run_id}/job/{jobId}#step:4:1"
    artifact_dir = os.path.join(args.results, entry['artifact'])
    result_file = os.path.join(artifact_dir, 'result.json')
    try:
      with open(result_file, 'r') as f:
        result: TestbedResult = mk_testbed_result(entry, json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
      continue
    results.append(result)
    if not result['doIndex']:
      logging.info(f"'{id}' opted-out of Reservoir")
      num_opt_outs +=1
    for build in walk_builds(result):
      build['url'] = url
      num_build_results += 1
      archive_size = build.get('archiveSize', None)
      if archive_size is not None:
        archive_sizes.append(archive_size)
      archive_hash = build.get('archiveHash', None)
      if archive_hash is None:
        continue
      archive = os.path.join(artifact_dir, f"{archive_hash}.barrel")
      if not os.path.exists(archive):
        logging.error(f"[{entry['jobName']}] Hash recorded for build archive, but file not found")
        continue
      content_hash = filehash(archive)
      if content_hash != archive_hash:
        logging.error(f"[{entry['jobName']}] Build archive hash does not matched recorded hash")
        continue
      if S3_ENABLED:
        upload_build(archive, archive_size, archive_hash)

  # Print stats
  logging.info(f"Package results: {len(results)} ({num_opt_outs} opt-outs)")
  num_archives = len(archive_sizes)
  logging.info(f"Build results: {num_build_results} ({num_archives} with archives)")
  total_size = sum(archive_sizes)
  logging.info(f'Total size of build archives: {fmt_bytes(total_size)} ({total_size} bytes)')
  avg = 0 if num_archives == 0 else round(total_size/num_archives)
  logging.info(f'Average build archive size: {fmt_bytes(avg)} ({avg} bytes)')

  # Output results
  if args.output is None:
    print(json.dumps(results, indent=2))
  else:
    with open(args.output, 'w') as f:
      f.write(json.dumps(results, indent=2))
