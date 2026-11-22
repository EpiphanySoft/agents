"""Every skill's frontmatter reads whole: its name is its folder's, and its description isn't cut short.

A description is a YAML scalar, so an unquoted one ends at the first " #" (YAML's comment) and a
": " can make it a mapping: either cut the description the skill list shows, and so what triggers it.
Run with `python3 tests/test_skill_frontmatter.py` from the repository's root (standard library only).
"""

import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path}: no frontmatter"
    return dict(line.split(": ", 1) for line in text.split("---\n")[1].splitlines() if line.strip())


class SkillFrontmatter(unittest.TestCase):
    def test_every_skill_names_its_folder_and_has_a_whole_description(self):
        skills = sorted(ROOT.glob("skills/*/SKILL.md"))
        self.assertTrue(skills)
        for path in skills:
            with self.subTest(skill=path.parent.name):
                fields = frontmatter(path)
                self.assertEqual(fields.get("name"), path.parent.name)
                raw = fields.get("description", "")
                if raw.startswith('"'):
                    value = json.loads(raw)  # a double-quoted scalar with JSON's escapes
                else:
                    self.assertNotIn(" #", raw, "unquoted: YAML ends it at ' #'; quote it")
                    self.assertNotIn(": ", raw, "unquoted: ': ' can break it; quote it")
                    value = raw
                self.assertGreater(len(value), 40)


if __name__ == "__main__":
    unittest.main()
