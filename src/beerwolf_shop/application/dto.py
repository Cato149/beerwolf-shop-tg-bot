"""Pydantic DTOs used by use cases (not HTTP-specific)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from beerwolf_shop.domain.enums import OrderType


class SubmitOrderDTO(BaseModel):
    customer_telegram_id: int
    display_name: str
    idea: str
    extra_contacts: str | None = None
    references: str | None = None
    budget: str | None = None
    username: str | None = None
    language: str = "ru"
    order_type: OrderType = OrderType.commission
    parent_order_id: UUID | None = None


class ManualOrderDTO(BaseModel):
    customer_telegram_id: int | None = None
    customer_username: str | None = None
    display_name: str
    idea: str
    extra_contacts: str | None = None
    references: str | None = None
    budget: str | None = None
    order_type: OrderType = OrderType.commission


class LinkGithubDTO(BaseModel):
    order_id: UUID
    repo_url: str
    project_display_name: str
    project_id: str | None = None


class CompleteOrderDTO(BaseModel):
    order_id: UUID
    links: list[tuple[str, str]] = Field(default_factory=list)
    message: str | None = None


class CustomerRequestDTO(BaseModel):
    order_id: UUID
    wish: str
    actor_telegram_id: int


class MilestoneSummary(BaseModel):
    number: int
    title: str
    due_on: str | None = None


class MilestoneTask(BaseModel):
    number: int
    title: str
    status: str
    due_on: str | None = None


class MilestoneDetails(BaseModel):
    number: int
    title: str
    due_on: str | None = None
    tasks: list[MilestoneTask] = Field(default_factory=list)


class ProgressSnapshot(BaseModel):
    total: int
    done: int
    percent: int
    bar: str
    in_progress: list[str]
    milestones: list[MilestoneSummary] = Field(default_factory=list)
    source: str = "project"
