#!/usr/bin/env python3
import json
import os
import re
import subprocess
import tempfile
from typing import Any, Dict
from urllib.parse import urljoin
from urllib.request import Request, urlopen

RE_PR_TITLE_FORMAT = re.compile(r'^Bump .+ from .+ to .+ in (?P<path>.+)$')

API_PREFIX: str = ''
API_TOKEN: str = ''

REPO_OWNER: str = ''
REPO_NAME: str = ''
PR_NUMBER: int = 0

FIXED_LABEL: str = ''

TERRAFORM_PREFIX: str = ''


def make_get_request(path: str, expected_status: int = 200) -> Dict[str, Any]:
    request = Request(urljoin(API_PREFIX, path))
    request.add_header('Authorization', f'token {API_TOKEN}')
    request.add_header('Accept', 'application/vnd.github.v3+json')
    with urlopen(request) as response:
        assert response.status == expected_status, response.status
        body = response.read().decode('utf-8')
        return json.loads(body)


def make_modify_request(method: str, path: str, body: Dict[str, Any], expected_status: int = 200) -> Dict[str, Any]:
    request = Request(urljoin(API_PREFIX, path), method=method, data=json.dumps(body).encode('utf-8'))
    request.add_header('Authorization', f'token {API_TOKEN}')
    request.add_header('Accept', 'application/vnd.github.v3+json')
    with urlopen(request) as response:
        assert response.status == expected_status, response.status
        body = response.read().decode('utf-8')
        return json.loads(body)


def main():
    # Get information about the PR.
    # See: https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request
    pr_payload = make_get_request(f'repos/{REPO_OWNER}/{REPO_NAME}/pulls/{PR_NUMBER}')

    # Bail if this is not a terraform dependabot PR.
    pr_label_names = {label['name'] for label in pr_payload.get('labels', [])}
    if not ('dependencies' in pr_label_names and 'terraform' in pr_label_names):
        print('Bailing as this is not a terraform dependabot PR.')
        return

    # Bail if this PR has already had this fixing up process applied to it.
    if FIXED_LABEL in pr_label_names:
        print('Bailing as this is PR has already had the fix applied.')
        return

    # Get information about our GitHub user.
    # See: https://docs.github.com/en/rest/users/users#get-the-authenticated-user
    user_payload = make_get_request('user')

    # Set our git commit identification.
    subprocess.check_call(['git', 'config', '--global', 'user.name', user_payload['name']])
    subprocess.check_call(['git', 'config', '--global', 'user.email', user_payload['email']])

    # Rewrite all SSH git operations to use HTTPS with our access token.
    subprocess.check_call(['git', 'config', '--global', f'url.https://oauth2:{API_TOKEN}@github.com.insteadOf', 'ssh://git@github.com'])

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
        terraform_path = os.path.join(TERRAFORM_PREFIX, terraform_version, 'terraform')

        # Ensure we have this version of terraform installed.
        if not os.path.exists(terraform_path):
            assert False, f'Required terraform version {terraform_version} is not installed.'

        # Initialize the terraform directory, ignoring errors.
        try:
            subprocess.run([terraform_path, 'init'])
        except subprocess.CalledProcessError:
            pass

        # Attempt to create the multiplatform hashes.
        subprocess.check_call([terraform_path, 'providers', 'lock', '-platform=darwin_amd64', '-platform=darwin_arm64', '-platform=linux_amd64'])

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
    make_modify_request('PATCH', f'repos/{REPO_OWNER}/{REPO_NAME}/issues/{PR_NUMBER}', {
        'labels': list(pr_label_names),
    })


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='A GitHub PR action for automatically adding terraform multiplatform hashes to a dependabot terraform PR.')
    parser.add_argument('--gh-api-prefix', default='https://api.github.com', help='The API prefix to make GitHub API requests to. You probably want to set this to be $GITHUB_API_URL')
    parser.add_argument('--gh-pr-number', required=True, type=int, help='The GitHub PR number. You probably want to extract this from $GITHUB_REF.')
    parser.add_argument('--gh-repository', required=True, help='The GitHub organisation/repository pair. You probably want to set this to be the $GITHUB_REPOSITORY')
    parser.add_argument('--gh-token-env-var', default='GITHUB_TOKEN', help='The name of the environment variable to read the GitHub auth token from.')
    parser.add_argument('--fixed-label', default='multiplatform-hashes', help='The name of the label to apply to PRs that have had this fix applied.')
    parser.add_argument('--terraform-bin-prefix', default='/opt/terraform', help='The location of where the different versions of terraform are installed.')
    args = parser.parse_args()

    API_PREFIX = args.gh_api_prefix
    API_TOKEN = os.environ[args.gh_token_env_var]
    PR_NUMBER = args.gh_pr_number
    REPO_OWNER, REPO_NAME = args.gh_repository.split('/')
    FIXED_LABEL = args.fixed_label
    TERRAFORM_PREFIX = args.terraform_bin_prefix

    main()
