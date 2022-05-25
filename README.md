This is a GitHub action definition for automatically updating dependabot terraform PRs to include multiplatform hashes.

This follows the conventions outlined in https://docs.github.com/en/actions/creating-actions/dockerfile-support-for-github-actions for supporting dockerised GitHub actions.

## Example usage

This requires having a secret (either repo or org level) called `DEPENDABOT_TERRAFORM_GITHUB_TOKEN`, which is a GitHub personal user token for a bot account that has access to the GitHub org where terraform dependencies are stored. It needs the following permissions:
* Ability to read and clone the repos where the target terraform modules are stored.
* Ability to read PRs on the current repo.
* Ability to add labels to issues on the current repo.
* Ability to commit to a branch on the current repo.
* Ability to read their own user profile.

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
    if: startsWith(github.head_ref, 'dependabot/')
    runs-on: ubuntu-latest
    env:
      GITHUB_TOKEN: ${{ secrets.DEPENDABOT_TERRAFORM_GITHUB_TOKEN }}
    steps:
      - name: Dependabot terraform multiplatform hashes
        id: multiplatform-hashes
        uses: airtasker/dependabot-terraform-multiplatform-hashes-action@main
```

## Useful links

* https://docs.github.com/en/actions/creating-actions/creating-a-docker-container-action
* https://docs.github.com/en/actions/creating-actions/dockerfile-support-for-github-actions
* https://docs.github.com/en/actions/learn-github-actions/environment-variables
