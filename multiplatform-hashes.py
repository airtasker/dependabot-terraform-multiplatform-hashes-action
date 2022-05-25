#!/usr/bin/env python3
"""
Set of available environment variables: https://docs.github.com/en/actions/learn-github-actions/environment-variables
"""
import json
import os
import re
import subprocess
import tempfile
from typing import Any, Dict
from urllib.parse import urljoin
from urllib.request import Request, urlopen

RE_PR_TITLE_FORMAT = re.compile(r'^Bump .+ from .+ to .+ in (?P<path>.+)$')

GH_API_PREFIX = os.environ['GITHUB_API_URL']
GH_REF = os.environ['GITHUB_REF']
GH_REPOSITORY = os.environ['GITHUB_REPOSITORY']
GH_TOKEN = os.environ['GITHUB_TOKEN']

COMMIT_USER_NAME = os.environ['INPUT_COMMIT_USER_NAME']
COMMIT_USER_EMAIL = os.environ['INPUT_COMMIT_USER_EMAIL']

TERRAFORM_PREFIX = '/opt/terraform'

REPO_OWNER, REPO_NAME = GH_REPOSITORY.split('/')
PR_NUMBER = int(re.sub(r'^refs/pull/(\d+)/merge$', r'\1', GH_REF))

FIXER_LABEL = 'multiplatform-hashes'


def make_get_request(path: str, expected_status: int = 200) -> Dict[str, Any]:
    request = Request(urljoin(GH_API_PREFIX, path))
    request.add_header('Authorization', f'token {GH_TOKEN}')
    request.add_header('Accept', 'application/vnd.github.v3+json')
    with urlopen(request) as response:
        assert response.status == expected_status, response.status
        body = response.read().decode('utf-8')
        return json.loads(body)


def make_modify_request(method: str, path: str, body: Dict[str, Any], expected_status: int = 200) -> Dict[str, Any]:
    json_payload = json.dumps(body)
    request = Request(urljoin(GH_API_PREFIX, path), method=method, data=json.dumps(body).encode('utf-8'))
    request.add_header('Authorization', f'token {GH_TOKEN}')
    request.add_header('Accept', 'application/vnd.github.v3+json')
    with urlopen(request) as response:
        assert response.status == expected_status, response.status
        body = response.read().decode('utf-8')
        return json.loads(body)


def main():
    # Get information about the PR.
    # See: https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request
    pr_payload = make_get_request(f'repos/{GH_REPOSITORY}/pulls/{PR_NUMBER}')

    # Bail if this is not a terraform dependabot PR.
    pr_label_names = {label['name'] for label in pr_payload.get('labels', [])}
    if not ('dependencies' in pr_label_names and 'terraform' in pr_label_names):
        print('Bailing as this is not a terraform dependabot PR.')
        return

    # Bail if this PR has already had this fixing up process applied to it.
    if FIXER_LABEL in pr_label_names:
        print('Bailing as this is PR has already had the fix applied.')
        return

    # Set our git commit identification.
    subprocess.check_call(['git', 'config', '--global', 'user.name', COMMIT_USER_NAME])
    subprocess.check_call(['git', 'config', '--global', 'user.email', COMMIT_USER_EMAIL])

    # Rewrite all SSH git operations to use HTTPS with our access token.
    subprocess.check_call(['git', 'config', '--global', f'url.https://oauth2:{GH_TOKEN}@github.com.insteadOf', 'ssh://git@github.com'])

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
    pr_label_names.add(FIXER_LABEL)
    make_modify_request('PATCH', f'repos/{GH_REPOSITORY}/issues/{PR_NUMBER}', {
        'labels': list(pr_label_names),
    })


if __name__ == '__main__':
    main()
