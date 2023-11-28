from server import app
from server.models import db


def seed_db():
    import flask_fixtures as ff
    import os
    seed_dir_paths = [os.path.join(app.config.get('BASE_DIR'), d)
                      for d in app.config.get('FIXTURES_DIRS')]
    seed_files_names = []
    seed_file_formats = set(['.yaml', '.yml', '.json'])

    for d in seed_dir_paths:
        for file in os.listdir(d):
            if not any([file.endswith(form) for form in seed_file_formats]):
                continue
            seed_files_names.append(file)

    for filename in seed_files_names:
        ff.load_fixtures_from_file(db, filename, seed_dir_paths)
