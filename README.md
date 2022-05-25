This is a GitHub action definition for automatically updating dependabot terraform PRs to include multiplatform hashes.

This follows the conventions outlined in https://docs.github.com/en/actions/creating-actions/dockerfile-support-for-github-actions for supporting dockerised GitHub actions.

## Example usage

```yaml
name: Dependabot terraform multiplatform hashes

on:
  pull_request:
    types:
      - opened
      - unlabeled
    branches:
      - master  # This is the *target* branch of the PR, not the head branch.

jobs:
  dependabot-terraform-multiplatform-hashes:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      issues: write
      pull-requests: read
    steps:
      - name: Dependabot terraform multiplatform hashes
        id: dependabot-terraform-multiplatform-hashes
        uses: airtasker/dependabot-terraform-multiplatform-hashes-action@main
        with:
          commit-user-name: 'GitHub Action user.'
          commit-user-email: 'automated@example.com'
          github-api-url: ${{ env.GITHUB_API_URL }}
          github-ref: ${{ env.GITHUB_REF }}
          github-repository: ${{ env.GITHUB_REPOSITORY }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Useful links

* https://docs.github.com/en/actions/creating-actions/creating-a-docker-container-action
* https://docs.github.com/en/actions/creating-actions/dockerfile-support-for-github-actions
* https://docs.github.com/en/actions/learn-github-actions/environment-variables
