"""HTTP schemas with OpenAPI descriptions for every field."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from beerwolf_shop.domain.enums import OrderStatus, OrderType


class HealthResponse(BaseModel):
    status: str = Field(description="Process liveness marker. Always `ok` if the app accepted the request.")


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(description="Raw Telegram Mini App initData query string, including the hash parameter.")


class TokenResponse(BaseModel):
    access_token: str = Field(description="JWT for customer API calls (Authorization: Bearer).")
    token_type: str = Field(default="bearer", description="Always `bearer`.")
    telegram_id: int = Field(description="Authenticated Telegram user id.")


class MeResponse(BaseModel):
    telegram_id: int = Field(description="Telegram user id.")
    username: str | None = Field(default=None, description="Telegram username without @, if known.")
    display_name: str = Field(description="Preferred display name collected during onboarding.")
    language: str = Field(description="UI language: `ru` or `en`.")
    is_admin: bool = Field(description="Whether this Telegram id is listed in ADMIN_TELEGRAM_IDS.")


class LanguageUpdate(BaseModel):
    language: str = Field(description="Target UI language: `ru` or `en`.")


class CompletionLinkOut(BaseModel):
    id: UUID = Field(description="Link identifier.")
    url: str = Field(description="Result URL shown to the customer.")
    title: str = Field(description="Human-readable label for the link.")


class OrderOut(BaseModel):
    id: UUID = Field(description="Order identifier.")
    type: OrderType = Field(description="`commission` or `support`.")
    status: OrderStatus = Field(description="Pipeline status.")
    customer_telegram_id: int = Field(description="Telegram id that receives notifications.")
    idea: str = Field(description="Request body / idea.")
    extra_contacts: str | None = Field(default=None, description="Optional extra contacts.")
    references: str | None = Field(default=None, description="Optional references.")
    budget: str | None = Field(default=None, description="Optional budget or timeline.")
    parent_order_id: UUID | None = Field(default=None, description="Parent commission for support tickets.")
    github_repo_url: str | None = Field(default=None, description="Linked GitHub repository HTML URL.")
    github_owner: str | None = Field(default=None, description="GitHub owner login.")
    github_repo: str | None = Field(default=None, description="GitHub repository name.")
    github_project_id: str | None = Field(default=None, description="Projects v2 node id.")
    github_milestone_number: int | None = Field(
        default=None,
        description="Dedicated GitHub milestone number for a support ticket.",
    )
    github_milestone_title: str | None = Field(
        default=None,
        description="Dedicated GitHub milestone title for a support ticket.",
    )
    project_display_name: str | None = Field(default=None, description="Name shown to the customer.")
    completion_message: str | None = Field(default=None, description="Extra text sent on completion.")
    created_at: datetime = Field(description="UTC creation timestamp.")
    updated_at: datetime = Field(description="UTC last update timestamp.")
    links: list[CompletionLinkOut] = Field(default_factory=list, description="Result links after completion.")
    photo_file_ids: list[str] = Field(
        default_factory=list,
        description="Telegram file_ids of photos the customer attached while submitting the request.",
    )


class OrderCreateIn(BaseModel):
    idea: str = Field(description="What the customer wants built.")
    display_name: str = Field(description="How to address the customer.")
    extra_contacts: str | None = Field(default=None, description="Optional extra contacts.")
    references: str | None = Field(default=None, description="Optional references.")
    budget: str | None = Field(default=None, description="Optional budget or timeline.")


class ManualOrderIn(BaseModel):
    customer_telegram_id: int | None = Field(default=None, description="Customer Telegram id (preferred).")
    customer_username: str | None = Field(default=None, description="Customer @username if the id is unknown.")
    display_name: str = Field(description="How to address the customer.")
    idea: str = Field(description="Request body.")
    extra_contacts: str | None = Field(default=None, description="Optional extra contacts.")
    references: str | None = Field(default=None, description="Optional references.")
    budget: str | None = Field(default=None, description="Optional budget.")
    type: OrderType = Field(default=OrderType.commission, description="Order type to create.")


class CompletionLinkIn(BaseModel):
    url: str = Field(description="Result URL.")
    title: str = Field(default="", description="Optional label; defaults to the URL.")


class StatusChangeIn(BaseModel):
    status: OrderStatus = Field(description="Target status.")
    github_repo_url: str | None = Field(
        default=None,
        description="Required when moving to `in_progress`. GitHub owner/repo URL.",
    )
    project_display_name: str | None = Field(
        default=None,
        description="Required when moving to `in_progress`. Customer-facing project name.",
    )
    github_project_id: str | None = Field(
        default=None,
        description="Projects v2 id. If omitted and several projects exist, the API returns 409 with options.",
    )
    links: list[CompletionLinkIn] | None = Field(
        default=None,
        description="Result links when moving to `completed`.",
    )
    message: str | None = Field(default=None, description="Extra completion message for the customer.")


class ProjectOption(BaseModel):
    id: str = Field(description="Projects v2 node id.")
    title: str = Field(description="Project title in GitHub.")


class ProjectChoiceResponse(BaseModel):
    detail: str = Field(description="Why the status change is not finished yet.")
    projects: list[ProjectOption] = Field(description="Projects v2 attached to the repository.")


class OrderListResponse(BaseModel):
    items: list[OrderOut] = Field(description="Page of orders.")
    total: int = Field(description="Total matching rows.")


class MilestoneSummaryOut(BaseModel):
    number: int = Field(description="Repository milestone number.")
    title: str = Field(description="Milestone title.")
    due_on: str | None = Field(default=None, description="GitHub due date, if configured.")
    total: int = Field(description="Total issues counted by GitHub for this milestone.")
    done: int = Field(description="Closed issues counted by GitHub for this milestone.")
    percent: int = Field(description="Milestone completion percent from 0 to 100.")


class MilestoneTaskOut(BaseModel):
    number: int = Field(description="GitHub issue number.")
    title: str = Field(description="Task title.")
    status: str = Field(description="Projects v2 status, or Open/Done fallback.")
    due_on: str | None = Field(default=None, description="Projects v2 due date, if configured.")
    labels: list[str] = Field(description="GitHub labels attached to the issue.")
    description: str = Field(description="GitHub issue body in its original Markdown form.")


class MilestoneDetailsOut(BaseModel):
    number: int = Field(description="Repository milestone number.")
    title: str = Field(description="Milestone title.")
    due_on: str | None = Field(default=None, description="Milestone due date, if configured.")
    total: int = Field(description="Total issues counted by GitHub for this milestone.")
    done: int = Field(description="Closed issues counted by GitHub for this milestone.")
    percent: int = Field(description="Milestone completion percent from 0 to 100.")
    tasks: list[MilestoneTaskOut] = Field(description="Issues assigned to the milestone.")


class ProgressOut(BaseModel):
    total: int = Field(description="Total tasks counted.")
    done: int = Field(description="Completed tasks.")
    percent: int = Field(description="Completion percent 0-100.")
    bar: str = Field(description="Text progress bar using ▓ and ░.")
    in_progress: list[str] = Field(description="Tasks currently in progress, with due dates when known.")
    milestones: list[MilestoneSummaryOut] = Field(description="Open milestones available for drill-down.")
    source: str = Field(description="`project` if Projects v2 was used, otherwise `repo` issues.")


class CustomerRequestIn(BaseModel):
    wish: str = Field(description="Customer's requested change. The Issue title is derived automatically.")


class CustomerRequestOut(BaseModel):
    html_url: str = Field(description="URL of the created GitHub issue.")


class SupportCreateIn(BaseModel):
    idea: str = Field(description="What needs a fix or follow-up.")
