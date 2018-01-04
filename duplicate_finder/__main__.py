import os
from pprint import pprint
import shutil

import click
import psutil
from termcolor import cprint

from database.mongodb import MongoDB
from database.sqlite import SQLite
from database.tinydb import TinyDB
from images import get_image_files, hash_files


DBs = {'mongodb': MongoDB,
       'sqlite': SQLite,
       'tinydb': TinyDB}

DB_LOCATIONS = {'mongodb': 'mongodb://localhost:27017',
                'sqlite': './db.sqlite',
                'tinydb': './db.json'}



@click.group()
@click.version_option(version='1.0')
@click.option('--db', type=click.Choice(sorted(DBs.keys())),
              default='tinydb', show_default=True)
@click.option('--db-location',
              help='The location of the database. This will change depending on the '
                   'database used. [defaults {}]'.format(
                        ', '.join(["{}: {}".format(name, loc)
                                   for name, loc in sorted(DB_LOCATIONS.items())])))
@click.pass_context
def cli(ctx, db, db_location):
    ctx.obj = DBs[db](DB_LOCATIONS[db])


@cli.command()
@click.argument('paths', nargs=-1, type=click.Path(exists=True))
@click.option('--parallel', default=psutil.cpu_count(), show_default=True)
@click.pass_obj
def add(db, paths, parallel):
    def new_image_files(files):
        for file in files:
            if db.contains(file):
                cprint("\tAlready hashed {}".format(file), "green")
            else:
                yield file

    for path in paths:
        cprint("Hashing {}".format(path), "blue")
        files = get_image_files(path)
        files = new_image_files(files)

        for file, result in hash_files(files, parallel):
            if result is None:
                cprint("\tUnable to open {}".format(file), "red")
                continue

            cprint("\tHashed {}".format(file), "blue")
            db.insert(result)

        cprint("...done", "blue")


@cli.command()
@click.argument('paths', nargs=-1, type=click.Path(exists=True))
@click.pass_obj
def remove(db, paths):
    total = 0

    for path in paths:
        cprint("Removing image files in database from {}".format(path), "blue")
        files = get_image_files(path)

        for file in files:
            cprint("\tRemoving {}".format(file), "green")
            db.remove(file)
            total += 1
        cprint("...done", "blue")

    cprint("Images removed in database: {}".format(total), "blue")


@cli.command()
@click.confirmation_option(prompt="Are you sure you want to clear the database?")
@click.pass_obj
def clear(db):
    db.clear()
    cprint("Database was cleared", "blue")


@cli.command()
@click.pass_obj
def show(db):
    pprint(db.all())
    cprint("Total: {}".format(db.count()), "blue")


@cli.command()
@click.option('--print', is_flag=True,
              help='Only print duplicate files rather than displaying HTML '
                   'file. This option takes priority over --delete.')
@click.option('--delete', is_flag=True,
              help='Move all found duplicate pictures to the trash.')
@click.option('--match-time', is_flag=True,
              help='Adds the extra constraint that duplicate images must have '
                   'the same capture times in order to be considered.')
@click.option('--trash', type=click.Path(),
              default='./Trash', show_default=True,
              help='Path to where files will be put when they are deleted.')
@click.pass_obj
def find(db, print, delete, match_time, trash):
    cprint("Finding duplicates...", "blue")
    duplicates = db.find_duplicates(match_time)
    cprint("...done", "blue")

    if print:
        pprint(duplicates)
        cprint("Number of duplicates: {}".format(len(duplicates)), "blue")
        return

    # Make the trash folder if necessary
    if not os.path.exists(trash):
        os.makedirs(trash)

    if delete:
        cprint("Deleting duplicates...", "blue")
        results = []
        for dup in duplicates:
            for file_info in dup['items'][1:]:
                results.append(delete_image(file_info['file_name'], db, trash))

        cprint("Deleted {}/{} files".format(results.count(True), len(results)),
               "yellow")
        cprint("...done", "blue")
    else:
        display_duplicates(duplicates, db, trash)


def delete_image(file_name, db, trash):
    cprint("\tMoving {} to {}".format(file_name, trash), 'yellow')

    try:
        shutil.move(file_name, os.path.join(trash, os.path.basename(file_name)))
        db.remove(file_name)
    except FileNotFoundError:
        cprint("\tFile not found {}".format(file_name), 'red')
        return False
    except Exception as e:
        cprint("\tError: {}".format(str(e)), 'red')
        return False

    return True


if __name__ == '__main__':
    cli()
