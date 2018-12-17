"""
Usage:
    write_manifest.py [options] <study>

Arguments:
    <study>             Name of the study to process

Options:
    -v --verbose             Verbose logger
    -d --debug                  Debug logger
    -q --quiet             Less debuggering
    
"""

from docopt import docopt
import sys, os, glob, logging, io, zipfile
import pydicom
import pandas as pd
import datman.config


logger = logging.getLogger(os.path.basename(__file__))

columns = ['source_name','PatientID','PatientName','StudyDate','StudyTime','visit','session','target_name','uploaded']
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

def get_manifest(filename):
    # Try to read manifest dataframe. If not present, create and read.
    try:
        return pd.read_csv(filename, dtype=dtypes) 
    except FileNotFoundError as e:
        logger.warning('{}. Creating manifest file.'.format(e))
        create_manifest(filename)
        return pd.read_csv(filename, dtype=dtypes)

def create_manifest(filename):
    #Creates empty manifest
    mf = pd.DataFrame(columns=columns)
    mf.to_csv(filename, index=False)

def get_headers(archive):
    # Get dicom header
    zf = zipfile.ZipFile(archive)
    for f in zf.namelist():
        try:
            header = pydicom.dcmread(io.BytesIO(zf.read(f)))    
            break
        except pydicom.filereader.InvalidDicomError:
            logger.debug('Invalid Dicom:{}'.format(f))
            continue
        except zipfile.BadZipfile:
            logger.warning('Error in zipfile:{}'.format(f))
            break    # Should be Return None, then maybe I don't need to del in main()
        #Or something like this: 
        #else: if no header, header = Null
    return header

def reindex_visits(dataframe):
    for index, row in dataframe.iterrows():
        if index == 0:
            continue
        prev_row = dataframe.iloc[index-1]

        if row['PatientName'] == prev_row['PatientName'] and row['StudyDate'] > prev_row['StudyDate']:
            dataframe.at[index, 'visit'] = prev_row['visit'] + 1
        elif row['PatientName'] == prev_row['PatientName'] and row['StudyDate'] == prev_row['StudyDate']:
            dataframe.at[index, 'visit'] = prev_row['visit']
    return dataframe

def reindex_sessions(dataframe):
    for index, row in dataframe.iterrows():
        if index == 0:
            continue
        prev_row = dataframe.iloc[index-1]

        if row['PatientName'] == prev_row['PatientName'] and row['StudyDate'] == prev_row['StudyDate'] and row['StudyTime'] > prev_row['StudyTime']:
            dataframe.at[index, 'session'] = prev_row['session'] + 1
        elif row['PatientName'] == prev_row['PatientName'] and row['StudyDate'] == prev_row['StudyDate'] and row['StudyTime'] == prev_row['StudyTime']:
            dataframe.at[index, 'session'] = prev_row['session']
    return dataframe

def generate_xnat_sessionIDs(study, dataframe):
    for index, row in dataframe.iterrows():
        if row['target_name'] == '<ignore>':
            continue
        subjectidwithsv = get_subjectid_with_sessionvisit(study, row['PatientName'])
        uid = (study + '_'
                + 'CMH_'
                + subjectidwithsv
                + '_MR')
        dataframe.at[index, 'target_name'] = uid
    return dataframe

def get_subjectid(study, patientid):
    if study == 'NUR02':
        patientid = patientid.replace('SCZ', '1')
        patientid = patientid.replace('HCT', '2')
        patientid = patientid.replace('FM', '3')
        patientid = patientid.replace('MG', '4')
        return patientid
    elif study == 'ALC01':
        patientid = patientid.replace('^', '')
        patientid = patientid.replace('-', '')
        patientid = patientid.replace('_', '')
        if patientid[2].isdigit():
            patientid = patientid[2:]
        return patientid
    else:
        return patientid

def get_subjectid_with_sessionvisit(study, patientid):
    patientid = patientid.replace('-', '_')
    patientid = patientid.split("_")
    try:
        patientid = patientid[2] + '_' + patientid[3] + '_SE' + patientid[4]
    except IndexError:
        logger.warning('Unable to create Participant ID: {}. Index Error.'.format(patientid))
        patientid = 'undefined'        
    return patientid

def main():
    arguments = docopt(__doc__)
    verbose = arguments['--verbose']
    debug = arguments['--debug']
    quiet = arguments['--quiet']
    study = arguments['<study>']

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

    formatter = logging.Formatter('%(asctime)s - %(name)s - {study} - %(levelname)s - %(message)s'.format(study=study))
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # Starting.
    print('###########################')
    print('##   WRITING MANIFEST    ##')
    print('###########################')

    # setup the config object
    cfg = datman.config.config(study=study)
    manifest_file = os.path.join(cfg.get_path('meta'), 'manifest.csv')
    zips_path = cfg.get_path('zips')
    if not os.path.isdir(zips_path):
        logger.error('Zips path {} doesnt exist'.format(zips_path))
        return
    
    # Pull up the manifest.
    mf = get_manifest(manifest_file)

    # Update manifest: for archive: if it's in manifest, skip, otherwise write.
    archive_list = [os.path.join(zips_path, a) for a in os.listdir(zips_path) if a.endswith('.zip')]
    for archive in archive_list:
        archive_basename = os.path.basename(archive).strip('.zip')
        if archive_basename in mf.source_name.values:
            logger.debug('Archive {} already in manifest, skipping...'.format(archive))
        else:
            logger.info('Adding archive {}'.format(archive))
            try:
                # Get dicom header from an archive.
                dh = get_headers(archive) 
                archive = str(archive_basename)
                patient_id = str(getattr(dh, 'PatientID', ''))
                patient_name = str(getattr(dh, 'PatientName', ''))
                study_date = int(getattr(dh, 'StudyDate', '0'))
                study_time = int(getattr(dh, 'StudyTime', '0'))
                # Append row to dataframe.
                row = pd.DataFrame([[archive, patient_id, patient_name, study_date, study_time, 1, 1, '', '']], columns=columns)
                mf = mf.append(row)
                logger.debug('Success')
            except NameError:
                logger.error('No headers for archive {} - skipping...'.format(archive))
                continue
    
    logger.info('Reindexing visits and sessions')

    mf.sort_values(['PatientName', 'StudyDate', 'StudyTime'], inplace=True)
    mf.reset_index(drop=True, inplace=True)

    mf = reindex_visits(mf)
    mf = reindex_sessions(mf)

    # Populate symlink column - code goes here
    logger.info('Generating XNAT session IDs')
    mf = generate_xnat_sessionIDs(study, mf)

    logger.info('Writing to csv')
    mf.to_csv(manifest_file, index=False)



    
    
if __name__ == "__main__":
    main()



    
