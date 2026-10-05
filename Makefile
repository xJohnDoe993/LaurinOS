.PHONY: check manifest release
check:
	python3 -B tools/check.py
manifest:
	python3 tools/build-manifest.py
release:
	python3 tools/build-release.py
