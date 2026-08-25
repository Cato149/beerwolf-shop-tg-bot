"""Aiogram FSM groups for wizards stored in Postgres."""

from aiogram.fsm.state import State, StatesGroup


class OrderWizard(StatesGroup):
    name = State()
    idea = State()
    contacts = State()
    references = State()
    budget = State()
    confirm = State()


class AdminManualWizard(StatesGroup):
    customer = State()
    name = State()
    idea = State()
    contacts = State()
    references = State()
    budget = State()
    confirm = State()


class AdminLinkGithub(StatesGroup):
    repo_url = State()
    project_name = State()
    project_choice = State()


class AdminComplete(StatesGroup):
    links = State()
    message = State()


class CustomerRequestWizard(StatesGroup):
    title = State()
    body = State()


class SupportWizard(StatesGroup):
    idea = State()
    contacts = State()
    references = State()
    budget = State()
    confirm = State()
