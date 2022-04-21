from pathlib import Path
import runpy

examples = Path(__file__).parent.parent / 'pyquerylist' / 'examples.py'


def test_examples():
    examples_results = runpy.run_path(examples)
    assert 'books' in examples_results
