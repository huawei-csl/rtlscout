# syntax=docker/dockerfile:1.4
# rtlscout layer on top of the rtlscout_base image (built from deps/tech_eval; rtlscout-owned, not
# the shared oss_eda_dev_base — build_image.sh builds rtlscout_base from scratch if absent).
#
# NOTE: Flowy / Mockturtle / ABC are intentionally NOT part of the public release.
# This layer therefore only adds the ELAU reference designs on top of the OSS EDA base
# (OpenROAD, Yosys, Verilator, OpenSTA, sv2v, svase, bender, morty, trace2power).

FROM rtlscout_base:latest

USER root

# ELAU reference designs (used by some agent prompts)
RUN git clone --depth 1 https://github.com/pulp-platform/ELAU /app/ELAU

USER vscode
WORKDIR /app
