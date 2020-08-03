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
    if [ "${APP_ID}" == "PLAYSTATION" ]; then
	echo "Type is CD, creating bin/cue"
	./rip_bincue.bash ${DRIVE} ${RIP_PATH} ${TEMP_STOR} ${APP_ID}
	sleep 5
	eject ${DRIVE}
	sleep 5
    else
	eject ${DRIVE}
    fi

done
