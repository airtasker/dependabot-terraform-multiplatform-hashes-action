#!/bin/sh
set -ue

# Grab the directory prefix of where to install the different versions of terraform.
PREFIX=${1}
shift

# Installed each requested version of terraform.
while [ ${#} -gt 0 ]; do
  VERSION=${1}
  shift

  D=${PREFIX}/${VERSION}
  mkdir -p ${D}
  curl https://releases.hashicorp.com/terraform/${VERSION}/terraform_${VERSION}_linux_amd64.zip -o ${D}/terraform.zip
  unzip -j ${D}/terraform.zip -d ${D}
  rm ${D}/terraform.zip
done
