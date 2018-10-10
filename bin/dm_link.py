#!/usr/bin/env python
"""
Renames (links) exam zip archives by consulting a lookup table.

This program looks up the proper name in a table that lists the original exam
archive name, and the target name.

Usage:
    dm_link.py [options] <study>
    dm_link.py [options] <study> <zipfile>

Arguments:
    <study>              Name of the study to process
    <zipfile>           Single Zipfile to process

Options:
    --lookup FILE            Path to scan id lookup table,
                                overrides metadata/manifest.csv
    --scanid-field STR       Dicom field to match target_name with
                             [default: PatientName]
    -v --verbose             Verbose logging
    -d --debug                  Debug logging
    -q --quiet             Less debuggering
    --dry-run             Dry run


DETAILS
    This program is used to rename an exam archive with their properly
    formatted scan names (see datman.scanid). Two approaches are used to find
    this name:

    ### Scan ID in a lookup table (--lookup)

    The lookup table should have atleast two columns: source_name, and
    target_name.  For example:

        source_name      target_name
        2014_0126_FB001  ASDD_CMH_FB001_01_01

    The source_name column is matched against the archive filename (so the
    entry above applies to 2014_0126_FB001.zip). The target_name column
    specifies the proper name for the exam.

    If the archive is not found in the lookup table, the dicom header is
    consulted:

    ### Scan ID in the dicom header (--scanid-field)

    Some scans may have the scan ID embedded in a dicom header field.

    The --scanid-field specifies a dicom header field to check for a
    well-formatted exam name.


ADDITIONAL MATCH CONDITIONS
    Additional columns in the lookup table can be specified to ensure that the
    DICOM headers of the file match what is expected. These column names should
    start with dicom_. For example,

        source_name      target_name            dicom_StudyID
        2014_0126_FB001  ASDD_CMH_FB001_01_01   512

    In the example above, this script would check that the StudyID field of an
    arbitrary dicom file in the archive contains the value "512". If not, an
    error is thrown.

IGNORING EXAM ARCHIVES
    Exam archives can be ignored by placing an entry into the lookup table with
    the target_name of '<ignore>', for example:
        source_name      target_name            dicom_StudyID
        2014_0126_FB001  <ignore>
"""
from docopt import docopt
import sys
import os
import glob
import pandas as pd
import datman.config
import datman.utils
import datman.scanid
import logging

logger = logging.getLogger(os.path.basename(__file__))
already_linked = {}
lookup = None
DRYRUN = None

dtypes = {'source_name':'object',
        'PatientID':'object',
        'PatientName':'object',
        'StudyDate':'int64',
        'StudyTime':'int64',
        'visit':'int64',
        'session':'int64',
        'target_name':'object',
        'uploaded':'object'
        }

#python 2 - 3 compatibility hack
try:
    basestring
except NameError:
    basestring = str

def main():
    # make the already_linked dict global as we are going to use it a lot
    global already_linked
    global lookup
    global DRYRUN

    arguments = docopt(__doc__)
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    DRYRUN = arguments['--dry-run']
    quiet = arguments['--quiet']
    study = arguments['<study>']
    lookup_path = arguments['--lookup']
    scanid_field = arguments['--scanid-field']
    zipfile = arguments['<zipfile>']

    # setup logging
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.WARN)
    logger.setLevel(logging.WARN)
    if quiet:
        logger.setLevel(logging.ERROR)
        ch.setLevel(logging.ERROR)
    if verbose:
        logger.setLevel(logging.INFO)
        ch.setLevel(logging.INFO)
    if debug:
        logger.setLevel(logging.DEBUG)
        ch.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s - %(name)s - {study} - '
                                  '%(levelname)s - %(message)s'.format(
                                  study=study))
    ch.setFormatter(formatter)

    logger.addHandler(ch)

    # Starting.
    print('###########################')
    print('##   CREATING SYMLINKS   ##')
    print('###########################')


    # setup the config object
    cfg = datman.config.config(study=study)
    if not lookup_path:
        lookup_path = os.path.join(cfg.get_path('meta'), 'manifest.csv')

    dicom_path = cfg.get_path('dicom')
    zips_path = cfg.get_path('zips')

    if not os.path.isdir(dicom_path):
        logger.warning('Dicom folder {} doesnt exist, creating it.'.format(
                dicom_path))
        try:
            os.makedirs(dicom_path)
        except IOError:
            logger.error('Failed to create dicom path {}'.format(dicom_path))
            return

    if not os.path.isdir(zips_path):
        logger.error('Zips path {} doesnt exist'.format(zips_path))
        return

    try:
        lookup = pd.read_csv(lookup_path, dtype=dtypes)
    except IOError:
        logger.error('Lookup file {} not found'.format(lookup_path))
        return

    # identify which zip files have already been linked
    already_linked = {os.path.realpath(f): f
                      for f
                      in glob.glob(os.path.join(dicom_path, '*'))
                      if os.path.islink(f)}

    if zipfile:
        if isinstance(zipfile, basestring):
            zipfile = [zipfile]
        archives = [os.path.join(zips_path, zip) for zip in zipfile]
    else:
        archives = [os.path.join(zips_path, archive)
                    for archive
                    in os.listdir(zips_path)
                    if os.path.splitext(archive)[1] == '.zip']

    logger.info('Found {} archives'.format(len(archives)))
    for archive in archives:
        link_archive(archive, dicom_path, scanid_field, cfg)


def link_archive(archive_path, dicom_path, scanid_field, config):
    if not os.path.isfile(archive_path):
        logger.error('Archive {} not found'.format(archive_path))
        return

    try:
        linked_path = already_linked[os.path.realpath(archive_path)]
    except KeyError:
        linked_path = ""

    if linked_path:
        logger.info("{} already linked at {}".format(archive_path, linked_path))
        return

    scanid = get_scanid_from_lookup_table(archive_path)

    # if scanid has been returned from the lookup table its a tuplet
    # otherwise None
    if scanid:
        scanid, lookupinfo = scanid

    if scanid == '<ignore>':
        logger.info('Ignoring {}'.format(archive_path))
        return

    # if we have a scan id, then validate any expected DICOM headers,
    # otherwise, check the DICOM headers for a valid scan id
    if scanid:
        if not validate_headers(archive_path, lookupinfo, scanid_field):
            logger.error('{}: Dicom headers do not match expected'
                         .format(archive_path))
            return
    else:
        scanid = get_scanid_from_header(archive_path, scanid_field)

    if not scanid:
        logger.error('Scanid not found for archive: {}'.format(archive_path))
        return

    ''' Should actually validate against our naming convention.
    try:
        datman.utils.validate_subject_id(scanid, config)
    except RuntimeError as e:
        logger.error(str(e) + ". Cannot make link for {}".format(archive_path))
        return
    '''

    # do the linking
    target = os.path.join(dicom_path, scanid)
    target = target + datman.utils.get_extension(archive_path)
    if os.path.exists(target):
        logger.error('Target: {} already exists for archive: {}'
                    .format(target, archive_path))
        return

    relpath = os.path.relpath(archive_path, dicom_path)
    logger.info('Linking {} to {}'.format(relpath, target))
    if not DRYRUN:
        os.symlink(relpath, target)


def get_scanid_from_lookup_table(archive_path):
    """
    Gets the scanid from the lookup table (pandas dataframe)

    Returns the scanid and the rest of the lookup table information (e.g.
    expected dicom header matches). If no match is found, both the scan id and
    lookup table info is None.
    """
    global lookup
    basename = os.path.basename(os.path.normpath(archive_path))
    source_name = basename[:-len(datman.utils.get_extension(basename))]
    lookupinfo = lookup[lookup['source_name'] == source_name]

    if len(lookupinfo) == 0:
        logger.debug("{} not found in source_name column."
                     .format(source_name))
        return
    else:
        scanid = lookupinfo['target_name'].tolist()[0]
        return (scanid, lookupinfo)


def get_archive_headers(archive_path):
    # get some DICOM headers from the archive
    header = None
    try:
        header = datman.utils.get_archive_headers(archive_path,
                                                  stop_after_first=True)
        header = header.values()[0]
    except:
        logger.warn("Archive: {} contains no DICOMs".format(archive_path))
    return header


def get_scanid_from_header(archive_path, scanid_field):
    """
    Gets the scanid from the dicom header object.

    Returns None if the header field isn't present or the value isn't a proper
    scan ID.
    """
    header = get_archive_headers(archive_path)
    if not header:
        return False
    if scanid_field not in header:
        logger.error("{} field is not in {} dicom headers"
                     .format(scanid_field, archive_path))
        return

    scanid = str(header.get(scanid_field))

    if datman.scanid.is_scanid(scanid):
        logger.debug("{}: Using scan ID from dicom field {} = {}."
                     .format(archive_path, scanid_field, scanid))
        return scanid
    else:
        logger.warn("{}: {} (header {}) not valid scan ID"
                    .format(archive_path, scanid, scanid_field))
        return None

def validate_headers(archive_path, lookupinfo, scanid_field):
    """
    Validates an exam archive against the lookup table

    Checks that all dicom_* dicom header fields match the lookup table
    """
    header = get_archive_headers(archive_path)
    if not header:
        return False

    columns = lookupinfo.columns.values.tolist()
    dicom_cols = [c for c in columns if c.startswith('dicom_')]

    for c in dicom_cols:
        f = c.split("_")[1]

        if f not in header:
            logger.error("{} field is not in {} dicom headers"
                         .format(scanid_field, archive_path))
            return False

        actual = str(header.get(f))
        expected = str(lookupinfo[c].tolist()[0])

        if actual != expected:
            logger.error("{}: dicom field '{}' = '{}', expected '{}'"
                         .format(archive_path, f, actual, expected))
            return False
    return True

if __name__ == '__main__':
    main()
