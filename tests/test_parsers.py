import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from oss_license_checker.parsers import npm, python, go  # noqa: E402


class NpmParserTest(unittest.TestCase):
    def test_parse_dependencies_and_dev(self):
        with tempfile.NamedTemporaryFile("w", suffix="package.json", delete=False) as f:
            f.write('{"dependencies":{"a":"^1.0.0"},"devDependencies":{"b":"^2.0.0"},"optionalDependencies":{"c":"*"}}')
            path = f.name
        try:
            deps = npm.parse(path)
            self.assertEqual(deps, {"a": "^1.0.0", "b": "^2.0.0", "c": "*"})
        finally:
            os.unlink(path)


class PythonParserTest(unittest.TestCase):
    def test_parse_requirements(self):
        content = "\n".join([
            "# comment",
            "requests==2.31.0",
            "numpy>=1.26",
            "pandas~=2.1.0",
            "redis",
            "django[argon2]>=4.2 ; python_version>='3.8'",
            "-r other.txt",
            "",
        ])
        with tempfile.NamedTemporaryFile("w", suffix="requirements.txt", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            deps = python.parse(path)
            self.assertEqual(deps["requests"], "2.31.0")
            self.assertEqual(deps["numpy"], "1.26")
            self.assertEqual(deps["pandas"], "2.1.0")
            self.assertEqual(deps["redis"], "*")
            self.assertEqual(deps["django"], "4.2")
            self.assertNotIn("other.txt", deps)
        finally:
            os.unlink(path)


class GoParserTest(unittest.TestCase):
    def test_parse_go_mod(self):
        content = "\n".join([
            "module example.com/x",
            "",
            "go 1.21",
            "",
            "require (",
            "\tgithub.com/gin-gonic/gin v1.9.1",
            "\tgithub.com/spf13/cobra v1.7.0",
            ")",
            "",
            "require github.com/sirupsen/logrus v1.9.0",
        ])
        with tempfile.NamedTemporaryFile("w", suffix="go.mod", delete=False) as f:
            f.write(content)
            path = f.name
        try:
            deps = go.parse(path)
            self.assertEqual(deps["github.com/gin-gonic/gin"], "v1.9.1")
            self.assertEqual(deps["github.com/spf13/cobra"], "v1.7.0")
            self.assertEqual(deps["github.com/sirupsen/logrus"], "v1.9.0")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
