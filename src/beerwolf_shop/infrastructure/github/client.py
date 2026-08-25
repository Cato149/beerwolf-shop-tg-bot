"""GitHub REST + GraphQL client (httpx)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from beerwolf_shop.domain.exceptions import GithubIntegrationError

logger = logging.getLogger(__name__)

REPO_URL_RE = re.compile(
    r"^(?:https?://github\.com/)?(?P<owner>[^/\s]+)/(?P<repo>[^/\s#]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)

CUSTOMER_REQUEST_LABEL = "customer request"


@dataclass(slots=True)
class GithubRepo:
    owner: str
    name: str
    url: str
    node_id: str


@dataclass(slots=True)
class GithubProject:
    id: str
    title: str


@dataclass(slots=True)
class GithubMilestone:
    title: str
    due_on: str | None
    open_issues: int
    closed_issues: int
    state: str


@dataclass(slots=True)
class GithubIssue:
    number: int
    title: str
    state: str
    body: str
    node_id: str
    html_url: str
    milestone_title: str | None
    milestone_due_on: str | None
    is_pull_request: bool


@dataclass(slots=True)
class ProjectItem:
    title: str
    state: str
    status: str | None
    due: str | None
    milestone_title: str | None
    milestone_due_on: str | None
    is_closed: bool


@dataclass(slots=True)
class ClosedIssuePayload:
    owner: str
    repo: str
    number: int
    title: str
    body: str
    last_comment: str | None
    html_url: str
    is_pull_request: bool


def parse_repo_url(value: str) -> tuple[str, str]:
    match = REPO_URL_RE.match(value.strip())
    if not match:
        raise GithubIntegrationError("invalid_repo_url")
    return match.group("owner"), match.group("repo")


class GithubClient:
    """Talks to GitHub REST (issues, milestones, hooks, labels) and GraphQL (Projects v2)."""

    def __init__(self, token: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._token = token
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "beerwolf-shop-tg-bot",
            },
            timeout=30.0,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _rest(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        allowed: tuple[int, ...] = (200, 201),
    ) -> httpx.Response:
        response = await self._client.request(method, path, json=json, params=params)
        if response.status_code not in allowed:
            logger.warning("GitHub REST %s %s -> %s %s", method, path, response.status_code, response.text[:500])
            raise GithubIntegrationError(f"github_http_{response.status_code}")
        return response

    async def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        response = await self._client.post(
            "https://api.github.com/graphql",
            json={"query": query, "variables": variables or {}},
        )
        if response.status_code != 200:
            raise GithubIntegrationError(f"github_graphql_http_{response.status_code}")
        payload = response.json()
        if payload.get("errors"):
            logger.warning("GitHub GraphQL errors: %s", payload["errors"])
            raise GithubIntegrationError("github_graphql_error")
        return payload.get("data") or {}

    async def get_repo(self, owner: str, repo: str) -> GithubRepo:
        response = await self._rest("GET", f"/repos/{owner}/{repo}")
        data = response.json()
        return GithubRepo(
            owner=data["owner"]["login"],
            name=data["name"],
            url=data["html_url"],
            node_id=data["node_id"],
        )

    async def list_milestones(self, owner: str, repo: str) -> list[GithubMilestone]:
        response = await self._rest(
            "GET",
            f"/repos/{owner}/{repo}/milestones",
            params={"state": "open", "per_page": 100, "sort": "due_date", "direction": "asc"},
            allowed=(200,),
        )
        result: list[GithubMilestone] = []
        for item in response.json():
            result.append(
                GithubMilestone(
                    title=item["title"],
                    due_on=item.get("due_on"),
                    open_issues=item.get("open_issues", 0),
                    closed_issues=item.get("closed_issues", 0),
                    state=item.get("state", "open"),
                )
            )
        result.sort(key=lambda m: (m.due_on is None, m.due_on or "", m.title.lower()))
        return result

    async def list_repo_issues(self, owner: str, repo: str) -> list[GithubIssue]:
        issues: list[GithubIssue] = []
        page = 1
        while page <= 5:
            response = await self._rest(
                "GET",
                f"/repos/{owner}/{repo}/issues",
                params={"state": "all", "per_page": 100, "page": page},
                allowed=(200,),
            )
            batch = response.json()
            if not batch:
                break
            for item in batch:
                issues.append(self._issue_from_rest(item))
            if len(batch) < 100:
                break
            page += 1
        return issues

    def _issue_from_rest(self, item: dict[str, Any]) -> GithubIssue:
        milestone = item.get("milestone") or {}
        return GithubIssue(
            number=item["number"],
            title=item.get("title") or "",
            state=item.get("state") or "open",
            body=item.get("body") or "",
            node_id=item.get("node_id") or "",
            html_url=item.get("html_url") or "",
            milestone_title=milestone.get("title"),
            milestone_due_on=milestone.get("due_on"),
            is_pull_request="pull_request" in item,
        )

    async def list_issue_comments(self, owner: str, repo: str, number: int) -> list[str]:
        response = await self._rest(
            "GET",
            f"/repos/{owner}/{repo}/issues/{number}/comments",
            params={"per_page": 100},
            allowed=(200,),
        )
        return [item.get("body") or "" for item in response.json()]

    async def ensure_label(self, owner: str, repo: str, name: str, color: str = "c5def5") -> None:
        encoded = quote(name)
        response = await self._client.get(f"/repos/{owner}/{repo}/labels/{encoded}")
        if response.status_code == 200:
            return
        await self._rest(
            "POST",
            f"/repos/{owner}/{repo}/labels",
            json={"name": name, "color": color},
            allowed=(201, 422),
        )

    async def create_issue(
        self,
        owner: str,
        repo: str,
        *,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> GithubIssue:
        response = await self._rest(
            "POST",
            f"/repos/{owner}/{repo}/issues",
            json={"title": title, "body": body, "labels": labels or []},
        )
        return self._issue_from_rest(response.json())

    async def ensure_issues_webhook(self, owner: str, repo: str, hook_url: str, secret: str) -> None:
        """Idempotently register an `issues` webhook pointing at this app."""
        response = await self._rest("GET", f"/repos/{owner}/{repo}/hooks", allowed=(200,))
        for hook in response.json():
            config = hook.get("config") or {}
            events = hook.get("events") or []
            if config.get("url") == hook_url and "issues" in events:
                return
        await self._rest(
            "POST",
            f"/repos/{owner}/{repo}/hooks",
            json={
                "name": "web",
                "active": True,
                "events": ["issues"],
                "config": {
                    "url": hook_url,
                    "content_type": "json",
                    "secret": secret,
                    "insecure_ssl": "0",
                },
            },
            allowed=(201, 422),
        )

    async def list_repository_projects(self, owner: str, repo: str) -> list[GithubProject]:
        data = await self.graphql(
            """
            query($owner: String!, $name: String!) {
              repository(owner: $owner, name: $name) {
                projectsV2(first: 20) {
                  nodes { id title }
                }
              }
            }
            """,
            {"owner": owner, "name": repo},
        )
        nodes = (((data.get("repository") or {}).get("projectsV2") or {}).get("nodes")) or []
        return [GithubProject(id=node["id"], title=node["title"]) for node in nodes if node]

    async def add_issue_to_project(self, project_id: str, content_id: str) -> str:
        data = await self.graphql(
            """
            mutation($projectId: ID!, $contentId: ID!) {
              addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
                item { id }
              }
            }
            """,
            {"projectId": project_id, "contentId": content_id},
        )
        item = ((data.get("addProjectV2ItemById") or {}).get("item")) or {}
        item_id = item.get("id")
        if not item_id:
            raise GithubIntegrationError("github_project_add_failed")
        return item_id

    async def set_project_status(
        self,
        project_id: str,
        item_id: str,
        status_field_name: str,
        option_name: str,
    ) -> None:
        """Set the single-select Status field on a Projects v2 item by option name."""
        data = await self.graphql(
            """
            query($id: ID!) {
              node(id: $id) {
                ... on ProjectV2 {
                  fields(first: 30) {
                    nodes {
                      ... on ProjectV2SingleSelectField {
                        id
                        name
                        options { id name }
                      }
                    }
                  }
                }
              }
            }
            """,
            {"id": project_id},
        )
        fields = (((data.get("node") or {}).get("fields") or {}).get("nodes")) or []
        field_id = None
        option_id = None
        for field in fields:
            if not field or field.get("name") != status_field_name:
                continue
            field_id = field["id"]
            for option in field.get("options") or []:
                if option.get("name") == option_name:
                    option_id = option["id"]
                    break
        if not field_id or not option_id:
            raise GithubIntegrationError("github_status_option_missing")
        await self.graphql(
            """
            mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
              updateProjectV2ItemFieldValue(
                input: {
                  projectId: $projectId
                  itemId: $itemId
                  fieldId: $fieldId
                  value: { singleSelectOptionId: $optionId }
                }
              ) { projectV2Item { id } }
            }
            """,
            {
                "projectId": project_id,
                "itemId": item_id,
                "fieldId": field_id,
                "optionId": option_id,
            },
        )

    async def list_project_items(self, project_id: str) -> list[ProjectItem]:
        data = await self.graphql(
            """
            query($id: ID!) {
              node(id: $id) {
                ... on ProjectV2 {
                  items(first: 100) {
                    nodes {
                      fieldValues(first: 15) {
                        nodes {
                          ... on ProjectV2ItemFieldSingleSelectValue {
                            name
                            field { ... on ProjectV2SingleSelectField { name } }
                          }
                          ... on ProjectV2ItemFieldDateValue {
                            date
                            field { ... on ProjectV2FieldCommon { name } }
                          }
                        }
                      }
                      content {
                        ... on Issue {
                          title
                          state
                          closed
                          milestone { title dueOn }
                        }
                      }
                    }
                  }
                }
              }
            }
            """,
            {"id": project_id},
        )
        nodes = (((data.get("node") or {}).get("items") or {}).get("nodes")) or []
        items: list[ProjectItem] = []
        for node in nodes:
            content = node.get("content") or {}
            if not content.get("title"):
                continue
            status = None
            due = None
            for value in (node.get("fieldValues") or {}).get("nodes") or []:
                field = value.get("field") or {}
                field_name = (field.get("name") or "").lower()
                if "name" in value and field_name == "status":
                    status = value.get("name")
                if "date" in value and field_name in {"due", "date", "due date"}:
                    due = value.get("date")
            milestone = content.get("milestone") or {}
            items.append(
                ProjectItem(
                    title=content.get("title") or "",
                    state=content.get("state") or "OPEN",
                    status=status,
                    due=due,
                    milestone_title=milestone.get("title"),
                    milestone_due_on=milestone.get("dueOn"),
                    is_closed=bool(content.get("closed")) or content.get("state") == "CLOSED",
                )
            )
        return items
