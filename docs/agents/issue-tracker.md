# Issue tracker: GitHub

Issues and specs live in `tiagoguerreirodev/monitorar-vacancias-perito-pf`.
Use the `gh` CLI from this repository.

## Conventions

- Create: `gh issue create --title "..." --body "..."`
  Use a heredoc for multiline bodies.
- Read: `gh issue view <number> --json number,title,body,labels,comments`
- List: `gh issue list --state open --json number,title,body,labels,comments`
  Add label and state filters as needed.
- Comment: `gh issue comment <number> --body "..."`
- Apply/remove labels: `gh issue edit <number> --add-label "..."` /
  `--remove-label "..."`
- Close: post an explanation with `gh issue comment`, then `gh issue close`.
  Comment separately even when the issue is already closed.

Infer the repository from the Git remote. Before the first issue creation
in a session, verify it with `gh repo view --json nameWithOwner`.
File issues only in the user's repository, not the skills' upstream repository.

## Parent issues and blockers

Use native GitHub sub-issues and issue dependencies when available.

With gh 2.94+:
- Create a child: `gh issue create --parent <parent> ...`
- Link an existing child: `gh issue edit <parent> --add-sub-issue <child>`
- Add a blocker: `gh issue edit <child> --add-blocked-by <blocker>`

With older gh versions, use the GitHub API:
- Sub-issue: POST `repos/{owner}/{repo}/issues/<parent>/sub_issues`
  with `sub_issue_id=<child-database-id>`.
- Dependency: POST `repos/{owner}/{repo}/issues/<child>/dependencies/blocked_by`
  with `issue_id=<blocker-database-id>`.

Get a database ID with:
`gh api repos/{owner}/{repo}/issues/<number> --jq .id`

If native relationships are unavailable, put `Part of #<parent>` and
`Blocked by: #<number>` lines at the top of the child body.
An issue is startable only when all its blockers are closed.

Count open native blockers with:
`gh api repos/{owner}/{repo}/issues/<number> --jq .issue_dependencies_summary.blocked_by`

## Pull requests as a triage surface

**PRs as a request surface: no.**

## Skill operations

- "Publish to the issue tracker": create a GitHub issue.
- "Fetch the relevant ticket": read the GitHub issue.

## Wayfinding operations

- Map: one issue labelled `wayfinder:map`, containing Notes,
  Decisions-so-far, and Fog.
- Child tickets: native sub-issues of the map, labelled
  `wayfinder:<type>` (`research`, `prototype`, `grilling`, or `task`).
  Fall back to a map task list and `Part of #<map>` in child bodies.
- Frontier: open map children with no open blocker and no assignee;
  take the first in map order.
- Claim: `gh issue edit <number> --add-assignee @me`.
- Resolve: comment with the answer, close the child, and append a
  context pointer (gist and link) to the map's Decisions-so-far.
