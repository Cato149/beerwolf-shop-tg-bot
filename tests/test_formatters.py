from beerwolf_shop.application.dto import MilestoneDetails, MilestoneTask
from beerwolf_shop.infrastructure.telegram.i18n import I18n
from beerwolf_shop.presentation.telegram.formatters import milestone_message, task_status_label


def test_task_statuses_are_localized_for_customers() -> None:
    i18n = I18n(default_locale="ru")
    assert task_status_label(i18n, "ru", "Ready") == "Скоро в работе"
    assert task_status_label(i18n, "ru", "In Progress") == "В работе"
    assert task_status_label(i18n, "ru", "Done") == "Готово"
    assert task_status_label(i18n, "ru", "Blocked") == "Blocked"


def test_milestone_tasks_are_quotes_with_labels_and_progress() -> None:
    i18n = I18n(default_locale="ru")
    details = MilestoneDetails(
        number=1,
        title="Первый этап",
        total=4,
        done=2,
        percent=50,
        tasks=[
            MilestoneTask(
                number=7,
                title="Нарисовать <лапу>",
                status="Ready",
                due_on="2026-09-15",
                labels=["design", "needs & review"],
                description="## Детали\n\nНужна **выразительная** форма и [референс](https://example.com).",
            )
        ],
    )

    text = milestone_message(i18n, "ru", details)

    assert "Готово: 2 из 4 · 50%" in text
    assert "<blockquote><b>Нарисовать &lt;лапу&gt;</b>" in text
    assert "Статус: Скоро в работе" in text
    assert "Срок: 2026-09-15" in text
    assert "Лейблы: design, needs &amp; review" in text
    assert "</blockquote>\n\n──────────\n<b>Детали</b>" in text
    assert "Нужна <b>выразительная</b> форма" in text
    assert '<a href="https://example.com">референс</a>' in text
