#!/bin/bash
source activate datman-env &&
python dm_sftp.py -d NUR02 &&
python write_manifest_NUR02.py -d NUR02 &&
python dm_link.py -d NUR02 &&
python dm_xnat_upload.py -d NUR02 &&
source deactivate &&
echo "###########################"
echo "##         DONE          ##"
echo "###########################"

