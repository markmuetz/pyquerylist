black:
	black -S -l120 .

release:
	python setup.py sdist
	twine upload dist/pyquerylist-*.tar.gz
