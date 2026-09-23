# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Gestor de disciplinas: loja persistente, skills (PT) e resumo."""

from __future__ import annotations

import datetime as dt

from jarvis.courses import Courses


def test_add_and_list_disciplines():
    c = Courses()
    d = c.add_discipline("Matemática", "Prof. Silva", "silva@escola.pt")
    assert d is not None and d["name"] == "Matemática"
    assert [x["name"] for x in c.list_disciplines()] == ["Matemática"]


def test_duplicate_and_empty_rejected():
    c = Courses()
    assert c.add_discipline("História") is not None
    assert c.add_discipline("história") is None  # case-insensitive dupe
    assert c.add_discipline("  ") is None


def test_resolve_by_name_and_id():
    c = Courses()
    d = c.add_discipline("Física")
    assert c.resolve("física") is d
    assert c.resolve(d["id"]) is d
    assert c.resolve("Inexistente") is None


def test_add_entries_and_validation():
    c = Courses()
    d = c.add_discipline("Química")
    assert c.add_test(d["id"], "2026-10-15", "Teste 1") is not None
    assert c.add_test(d["id"], "bad-date") is None  # invalid date rejected
    assert c.add_task(d["id"], "2026-10-20", "Projeto") is not None
    assert c.add_absence(d["id"], "2026-09-30", "doente") is not None
    assert c.add_note(d["id"], "Rever ligações — informação") is not None
    assert c.add_note(d["id"], "  ") is None  # empty note rejected
    d2 = c.get_discipline(d["id"])
    assert len(d2["tests"]) == 1 and len(d2["tasks"]) == 1
    assert len(d2["absences"]) == 1 and len(d2["notes"]) == 1
    # Accents preserved.
    assert d2["notes"][0]["text"] == "Rever ligações — informação"


def test_toggle_and_remove():
    c = Courses()
    d = c.add_discipline("Inglês")
    t = c.add_test(d["id"], "2026-11-01")
    assert c.toggle_done(d["id"], "tests", t["id"]) is True
    assert c.get_discipline(d["id"])["tests"][0]["done"] is True
    assert c.remove_entry(d["id"], "tests", t["id"]) is True
    assert c.get_discipline(d["id"])["tests"] == []


def test_persistence():
    c1 = Courses()
    c1.add_discipline("Biologia")
    c2 = Courses()  # same temp store dir via fixture
    assert c2.resolve("Biologia") is not None


def test_upcoming_within_window():
    c = Courses()
    d = c.add_discipline("Geografia")
    soon = (dt.date.today() + dt.timedelta(days=3)).isoformat()
    far = (dt.date.today() + dt.timedelta(days=40)).isoformat()
    c.add_test(d["id"], soon, "Perto")
    c.add_task(d["id"], far, "Longe")
    up = c.upcoming(7)
    assert len(up) == 1 and up[0]["title"] == "Perto"
    assert up[0]["discipline"] == "Geografia"


def test_upcoming_excludes_done():
    c = Courses()
    d = c.add_discipline("Artes")
    soon = (dt.date.today() + dt.timedelta(days=2)).isoformat()
    t = c.add_test(d["id"], soon)
    c.toggle_done(d["id"], "tests", t["id"])
    assert c.upcoming(7) == []


# -- skills (via the registry, PT replies) ---------------------------------


def test_course_skills_registered(registry):
    for name in ("add_discipline", "list_disciplines", "add_course_test",
                 "add_course_task", "mark_absence", "add_course_note",
                 "course_summary"):
        assert registry.has(name), name


def test_skill_add_and_error_flow(registry):
    out = registry.dispatch("add_discipline", {"name": "Matemática", "teacher": "Silva"})
    assert "Matemática" in out and "Silva" in out
    # Test on a missing discipline -> PT error.
    err = registry.dispatch("add_course_test", {"discipline": "Nada", "date": "2026-10-10"})
    assert err.startswith("[error]") and "Não encontrei" in err
    # Bad date -> PT error.
    bad = registry.dispatch("add_course_test", {"discipline": "Matemática", "date": "xx"})
    assert bad.startswith("[error]") and "AAAA-MM-DD" in bad


def test_skill_summary_pt(registry):
    registry.dispatch("add_discipline", {"name": "Redes"})
    soon = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    registry.dispatch("add_course_test", {"discipline": "Redes", "date": soon, "title": "T1"})
    out = registry.dispatch("course_summary", {"days": 7})
    assert "Redes" in out and "teste" in out.lower()


# -- horário e classificações ----------------------------------------------


def test_new_disciplines_have_schedule_and_grades():
    c = Courses()
    d = c.add_discipline("Programação")
    assert d["schedule"] == [] and d["grades"] == []


def test_add_class_orders_by_weekday():
    c = Courses()
    d = c.add_discipline("Matemática")
    c.add_class(d["id"], "Quarta", "10:00", "11:30", "B12")
    c.add_class(d["id"], "Segunda", "08:00", "09:30", "A1")
    sched = c.get_discipline(d["id"])["schedule"]
    assert [a["weekday"] for a in sched] == ["Segunda", "Quarta"]  # ordenado
    assert sched[0]["room"] == "A1"


def test_add_class_requires_weekday():
    c = Courses()
    d = c.add_discipline("Física")
    assert c.add_class(d["id"], "  ") is None


def test_add_grade_and_validation():
    c = Courses()
    d = c.add_discipline("Química")
    assert c.add_grade(d["id"], "Teste 1", "15") is not None
    assert c.add_grade(d["id"], "", "15") is None       # sem nome
    assert c.add_grade(d["id"], "Ficha", "") is None    # sem valor
    assert len(c.get_discipline(d["id"])["grades"]) == 1


def test_set_grade_on_test():
    c = Courses()
    d = c.add_discipline("Inglês")
    t = c.add_test(d["id"], "2026-11-01", "Oral")
    assert t["grade"] == ""  # começa vazio
    assert c.set_grade(d["id"], "tests", t["id"], "18") is True
    assert c.get_discipline(d["id"])["tests"][0]["grade"] == "18"
    # kind inválido
    assert c.set_grade(d["id"], "absences", t["id"], "10") is False


def test_remove_class_and_grade():
    c = Courses()
    d = c.add_discipline("Artes")
    a = c.add_class(d["id"], "Sexta", "14:00", "15:30")
    g = c.add_grade(d["id"], "Projeto", "17")
    assert c.remove_entry(d["id"], "schedule", a["id"]) is True
    assert c.remove_entry(d["id"], "grades", g["id"]) is True
    disc = c.get_discipline(d["id"])
    assert disc["schedule"] == [] and disc["grades"] == []
