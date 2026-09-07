#!/usr/bin/env python3
"""Build reproducible service skill archives alongside the Direct Skill."""
import pathlib
import stat
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILLS = {
    'agentcart-service-skill': ROOT / 'gateway/openclaw-skill',
    'household-os-skill': ROOT / 'household-os/openclaw-skill',
}


def package_skills():
    destination = ROOT / 'dist'
    destination.mkdir(exist_ok=True)
    for slug, source in SKILLS.items():
        if not (source / 'SKILL.md').is_file():
            raise ValueError(f'Skill missing: {source}')
        with zipfile.ZipFile(destination / f'{slug}.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(source.rglob('*')):
                relative = path.relative_to(source)
                if not path.is_file() or path.is_symlink() or path.suffix == '.pyc' or any(part.startswith('.') or part == '__pycache__' for part in relative.parts):
                    continue
                entry = zipfile.ZipInfo(f'{slug}/{relative.as_posix()}', date_time=(2000, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = (stat.S_IMODE(path.stat().st_mode) | stat.S_IFREG) << 16
                archive.writestr(entry, path.read_bytes())
        print(f'Created {destination / (slug + ".zip")}')


if __name__ == '__main__':
    package_skills()
