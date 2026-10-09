# SNES core metadata fallback

Source: https://github.com/libretro/libretro-core-info
Retrieved 2026-10-09 from master; original metadata files, MIT license in COPYING.

These files describe the two SNES cores supported by PaimenOS. Installed system
metadata takes priority. Bundled metadata covers existing/offline installations
and direct-download cores without requiring package reinstallation.

RetroArch 1.14 and 1.20 gate save/load operations on this metadata before calling
the core serialization API. PaimenOS explicitly sets both libretro_directory to
the loaded core's directory and libretro_info_path to the matching metadata.
The info cache is disabled to avoid retaining a previous missing-info result.
This does not add serialization support to a core or bypass its runtime check.
