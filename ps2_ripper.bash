#!/bin/bash

DRIVE=/dev/sr0
RIP_PATH=/psx
TEMP_STOR=/tmp/wav

mkdir -p ${TEMP_STOR}

while sleep 15
do
    udevadm info --query=property ${DRIVE} | grep ID_CDROM_MEDIA=1
    while [ $? -ne 0 ]
    do
	sleep 15
	echo -n "."
	udevadm info --query=property ${DRIVE} | grep ID_CDROM_MEDIA=1
    done
    sleep 15

    DISCDATA=$(udevadm info --query=property ${DRIVE})

    APP_ID=$(echo ${DISCDATA} | xargs -n1 echo | grep ^ID_FS_APPLICATION_ID= | cut -d = -f2)
    ID_FS_TYPE=$(echo ${DISCDATA} | xargs -n1 echo | grep ^ID_FS_TYPE= | cut -d = -f2)

    if [ "${APP_ID}" == "PLAYSTATION" ]; then
	echo "Type is CD, creating bin/cue"
	./rip_bincue.bash ${DRIVE} ${RIP_PATH} ${TEMP_STOR} ${APP_ID}_2
    elif [ "${ID_FS_TYPE}" == "udf" ]; then
	echo "Type is UDF, assuming PS2 DVD"
	mkdir -p ${RIP_PATH}/PLAYSTATION_2
	ddrescue -b 2048 ${DRIVE} ${RIP_PATH}/ps2_temp_iso.iso
	# now do something cool with python
	DISCNAME=$(./get_ps2_name.py ${RIP_PATH}/ps2_temp_iso.iso)
	# move the file to PLAYSTATION_2
	if [ -f "${RIP_PATH}/PLAYSTATION_2/${DISCNAME}.iso" ]; then
	    echo "File already exists, making copy"
	    DS=$(date +%s)
	    mv ${RIP_PATH}/ps2_temp_iso.iso "${RIP_PATH}/PLAYSTATION_2/${DISCNAME}_${DS}.iso"
	else
	    mv ${RIP_PATH}/ps2_temp_iso.iso "${RIP_PATH}/PLAYSTATION_2/${DISCNAME}.iso"
	fi
	echo "Finished ${DISCNAME}"
    fi

    sleep 5
    eject ${DRIVE}
    sleep 5
done
