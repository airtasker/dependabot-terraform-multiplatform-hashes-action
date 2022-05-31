#!/usr/bin/env python3
import io
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
from urllib.request import Request, urlopen

RE_MAYBE_SECRET = re.compile(r'.*_(secret|token|key)$', re.I)
RE_PR_TITLE_FORMAT = re.compile(r'^Bump .+ from .+ to .+ in (?P<path>.+)$')

API_PREFIX: str = ''
API_TOKEN_LIGHT: str = ''
API_TOKEN_FULL: str = ''

REPO_OWNER: str = ''
REPO_NAME: str = ''
PR_NUMBER: int = 0

FIXED_LABEL: str = ''

TERRAFORM_PLATFORMS: List[str] = []


def abort_empty_api_token(is_full: bool):
    out = io.StringIO()
    for k, v in sorted(os.environ.items()):
        obfuscated_v = v
        if RE_MAYBE_SECRET.match(k):
            if len(v) > 6:
                obfuscated_v = ('*' * (len(v) - 3)) + v[-3:]
            else:
                obfuscated_v = '*' * len(v)
        out.write(f'  {k}: {obfuscated_v} ({len(v)})\n')
    logging.error('Failed to find %s API token in environment variable. Aborting. Environment was:\n%s', 'full' if is_full else 'light', out.getvalue())
    sys.exit(1)


def make_request(api_token: str, method: str, path: str, body: Optional[bytes], expected_status: int = 200) -> Dict[str, Any]:
    request = Request(urljoin(API_PREFIX, path), method=method, data=body)
    request.add_header('Authorization', f'token {api_token}')
    request.add_header('Accept', 'application/vnd.github.v3+json')
    logging.info('Making a %s request to %s.', request.get_method(), request.get_full_url())
    with urlopen(request) as response:
        assert response.status == expected_status, response.status
        body = response.read().decode('utf-8')
        return json.loads(body)


def make_get_request(api_token: str, path: str, expected_status: int = 200) -> Dict[str, Any]:
    return make_request(api_token, 'GET', path, None, expected_status)


def make_modify_request(api_token: str, method: str, path: str, body: Dict[str, Any], expected_status: int = 200) -> Dict[str, Any]:
    return make_request(api_token, method, path, json.dumps(body).encode('utf-8'), expected_status)


def main():
    # Get information about the PR.
    # See: https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request
    pr_payload = make_get_request(API_TOKEN_LIGHT, f'repos/{REPO_OWNER}/{REPO_NAME}/pulls/{PR_NUMBER}')

    # Bail if this is not a terraform dependabot PR.
    pr_label_names = {label['name'] for label in pr_payload.get('labels', [])}
    if not ('dependencies' in pr_label_names and 'terraform' in pr_label_names):
        logging.info('Bailing as this is not a terraform dependabot PR.')
        return

    # Bail if this PR has already had this fixing up process applied to it.
    if FIXED_LABEL in pr_label_names:
        logging.info('Bailing as this is PR has already had the fix applied.')
        return

    # Ensure we have an API token.
    if not API_TOKEN_FULL:
        abort_empty_api_token(True)

    # Get information about our GitHub user.
    # See: https://docs.github.com/en/rest/users/users#get-the-authenticated-user
    user_payload = make_get_request(API_TOKEN_FULL, 'user')
    user_name = (user_payload.get('name') or '').strip() or user_payload['login']
    # See: https://docs.github.com/en/rest/users/emails#list-email-addresses-for-the-authenticated-user
    user_email_payload = make_get_request(API_TOKEN_FULL, 'user/emails')
    user_email = [p['email'] for p in user_email_payload if p['primary']][0]

    # Set our git commit identification.
    subprocess.check_call(['git', 'config', '--global', 'user.name', user_name])
    subprocess.check_call(['git', 'config', '--global', 'user.email', user_email])

    # Rewrite all SSH git operations to use HTTPS with our access token.
    subprocess.check_call(['git', 'config', '--global', f'url.https://oauth2:{API_TOKEN_FULL}@github.com.insteadOf', 'ssh://git@github.com'])

    # Obtain the terraform project path from the PR title.
    pr_title = pr_payload['title']
    parts = RE_PR_TITLE_FORMAT.match(pr_title)
    assert parts is not None, pr_title
    terraform_project_path = parts.group('path').lstrip('/')

    # Inside a temporary directory...
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)

        # Work out the URL to clone the repository via. The API returns us a SSH clone URL of the
        # form `git@github.com:owner/repo`, which does not work with our git SSH rewrite rule to
        # use HTTPS instead. So, we restructure this to be an alternative form of SSH clone URL
        # that git supports: `https://git@github.com/repo/owner`.
        repo_clone_url = 'ssh://' + pr_payload['head']['repo']['ssh_url'].replace(':', '/', 1)

        # Clone the repository.
        pr_branch_name = pr_payload['head']['ref']
        subprocess.check_call(['git', 'clone', '--depth', '1', '--branch', pr_branch_name, repo_clone_url, REPO_NAME])

        # Change directory to the terraform project.
        os.chdir(os.path.join(REPO_NAME, terraform_project_path))

        # Work out which version of terraform to use.
        with open('.terraform-version') as f:
            terraform_version = f.read().strip()

        # Download the appropriate version of terraform.
        logging.info('Downloading terraform version %s', terraform_version)
        subprocess.check_call(['curl', f'https://releases.hashicorp.com/terraform/{terraform_version}/terraform_{terraform_version}_linux_amd64.zip', '-o', 'terraform.zip'])
        subprocess.check_call(['unzip', '-j', 'terraform.zip', '-d', '/'])
        subprocess.check_call(['rm', 'terraform.zip'])
        terraform_path = '/terraform'

        # Initialize the terraform directory, ignoring errors.
        logging.info('Initialising terraform project.')
        try:
            subprocess.check_call([terraform_path, 'init'])
        except subprocess.CalledProcessError:
            pass

        # Attempt to create the multiplatform hashes.
        logging.info('Updating provider hashes.')
        subprocess.check_call([terraform_path, 'providers', 'lock'] + [f'-platform={p}' for p in TERRAFORM_PLATFORMS])

        # Commit and push any changes to the lock file. We catch the error on commit as it is
        # possible that no changes were made, at which point `git commit` fails as there's nothing
        # to commit.
        subprocess.check_call(['git', 'add', '.terraform.lock.hcl'])
        try:
            subprocess.check_call(['git', 'commit', '-m', 'Multiplatform hashes.'])
        except subprocess.CalledProcessError:
            pass
        else:
            subprocess.check_call(['git', 'push'])

    # Add the fixed label to the PR so that the fixer process does not attempt to run again.
    pr_label_names.add(FIXED_LABEL)
    make_modify_request(API_TOKEN_LIGHT, 'PATCH', f'repos/{REPO_OWNER}/{REPO_NAME}/issues/{PR_NUMBER}', {
        'labels': list(pr_label_names),
    })
    logging.info('Finished applying multiplatform hashes fix to PR #%d.', PR_NUMBER)


if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        level=logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    import argparse

    parser = argparse.ArgumentParser(description='A GitHub PR action for automatically adding terraform multiplatform hashes to a dependabot terraform PR.')
    parser.add_argument('--gh-api-prefix', default='https://api.github.com', help='The API prefix to make GitHub API requests to. You probably want to set this to be $GITHUB_API_URL')
    parser.add_argument('--gh-pr-number', required=True, type=int, help='The GitHub PR number. You probably want to extract this from $GITHUB_REF.')
    parser.add_argument('--gh-repository', required=True, help='The GitHub organisation/repository pair. You probably want to set this to be the $GITHUB_REPOSITORY')
    parser.add_argument('--gh-token-light-env-var', default='GITHUB_TOKEN', help='The name of the environment variable to read the light access GitHub auth token from.')
    parser.add_argument('--gh-token-full-env-var', default='DEPENDABOT_TERRAFORM_GITHUB_TOKEN', help='The name of the environment variable to read the full access GitHub auth token from.')
    parser.add_argument('--fixed-label', default='multiplatform-hashes', help='The name of the label to apply to PRs that have had this fix applied.')
    parser.add_argument('--terraform-platforms', default='darwin_amd64,linux_amd64', help='Comma separated list of the terraform platforms to fetch the hashes for.')
    args = parser.parse_args()

    API_PREFIX = args.gh_api_prefix
    API_TOKEN_LIGHT = os.environ[args.gh_token_light_env_var]
    API_TOKEN_FULL = os.environ.get(args.gh_token_full_env_var, '')
    PR_NUMBER = args.gh_pr_number
    REPO_OWNER, REPO_NAME = args.gh_repository.split('/')
    FIXED_LABEL = args.fixed_label
    TERRAFORM_PLATFORMS = [p.strip() for p in args.terraform_platforms.split(',')]

    logging.info('Running with the following configuration:')
    logging.info('  API_PREFIX: %s', API_PREFIX)
    logging.info('  API_TOKEN_LIGHT: ...%s (reading from environment variable %s; length %d)', API_TOKEN_LIGHT[-3:], args.gh_token_light_env_var, len(API_TOKEN_LIGHT))
    logging.info('  API_TOKEN_FULL: ...%s (reading from environment variable %s; length %d)', API_TOKEN_FULL[-3:], args.gh_token_full_env_var, len(API_TOKEN_FULL))
    logging.info('  PR_NUMBER: %d', PR_NUMBER)
    logging.info('  REPO_OWNER: %s', REPO_OWNER)
    logging.info('  REPO_NAME: %s', REPO_NAME)
    logging.info('  FIXED_LABEL: %s', FIXED_LABEL)
    logging.info('  TERRAFORM_PLATFORMS: %s', TERRAFORM_PLATFORMS)

    # Ensure we have an API token.
    if not API_TOKEN_LIGHT:
        abort_empty_api_token(False)

    main()
