# from: https://github.com/huawei-csl/oss_eda_dev_base/blob/main/Dockerfile
# SPDX-License-Identifier: BSD-3-Clause Clear
# Copyright (c) 2024-2025 HUAWEI.
# All rights reserved.
#
# This software is released under the BSD 3-Clause Clear License.
# See the LICENSE file in the project root for full license information (https://github.com/huawei-csl/oss_eda_dev_base).

# syntax=docker/dockerfile:1.4
# Optimized OSS EDA Base image (size-reduced)
# - Multi-stage builds for heavy tools (build deps never enter final image)
# - Shallow clones, strip binaries, remove build trees/caches
# - Separate build deps (purged) vs runtime deps
#
# Final stage provides:
# - OpenROAD binary
# - Verilator
# - Yosys (+ yosys-slang)
# - OpenSTA (+ CUDD + Eigen runtime)
# - sv2v, svase, bender, morty
# - trace2power
# - uv-managed Python 3.13 venv with core libs

########## Common ARGs ##########
ARG NPROC=8
ARG VERILATOR_VER="v5.040"
ARG YOSYS_VER="v0.55"
ARG OPENSTA_REPO="https://github.com/The-OpenROAD-Project/OpenSTA"
ARG EIGEN_REPO="https://gitlab.com/libeigen/eigen.git"
ARG CUDD_REPO="https://github.com/davidkebo/cudd"
ARG ORFS_REPO="https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts"
ARG ASAP7_REPO="https://github.com/The-OpenROAD-Project/asap7sc7p5t_28.git"

########## Builder: base (common build deps) ##########
FROM ubuntu:24.04 AS builder-base
SHELL ["/bin/bash","-lc"]
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl wget git unzip zip \
    build-essential g++ make cmake ninja-build \
    autoconf automake libtool pkg-config \
    flex bison help2man \
    libfl-dev \
    zlib1g-dev libreadline-dev libffi-dev tcl-dev \
    swig python3.12-minimal python3.12-venv python3.12-dev \
    libgoogle-perftools-dev numactl \
    libboost-system-dev libboost-filesystem-dev libboost-python-dev \
    libgtest-dev \
    locales graphviz xdot gawk \
 && rm -rf /var/lib/apt/lists/*

########## Builder: OpenROAD (from ORFS) ##########
FROM builder-base AS build-openroad
ARG ORFS_REPO
ARG NPROC
RUN git clone --depth 1 "${ORFS_REPO}" /build/ORFS
WORKDIR /build/ORFS
# Fetch exactly that commit into the shallow clone and check it out
# RUN git fetch --no-tags --depth 1 origin 9c88e25970729dcaf7af59ffd7c98c168c5a2c71 \
#  && git checkout --detach 9c88e25970729dcaf7af59ffd7c98c168c5a2c71 \
#  && git submodule update --init --recursive --depth 1
RUN set -eu; \
  tmpdir="$(mktemp -d)"; trap 'rm -rf "$tmpdir"' EXIT; \
  { \
    echo 'cmake_minimum_required(VERSION 3.16)'; \
    echo 'project(pycheck LANGUAGES C)'; \
    echo 'find_package(Python3 REQUIRED COMPONENTS Interpreter Development Development.Module Development.Embed)'; \
  } > "$tmpdir/CMakeLists.txt"; \
  cmexe="$(command -v python3)"; \
  cmake -S "$tmpdir" -B "$tmpdir/build" -DPython3_EXECUTABLE="$cmexe" -DPython3_FIND_STRATEGY=LOCATION -DPython3_FIND_IMPLEMENTATIONS=CPython -Werror=dev
RUN set -eux; \
  sed -i 's/sudo -u \$SUDO_USER //g' setup.sh; \
  ./setup.sh;
RUN ./build_openroad.sh --local --openroad-args "-DENABLE_TESTS=OFF"; \
  mkdir -p /opt/tools/openroad; \
  cp -a tools/install/OpenROAD /opt/tools/openroad/

########## Builder: Verilator ##########
FROM builder-base AS build-verilator
ARG VERILATOR_VER
ARG NPROC
RUN git clone --depth 1 --branch "${VERILATOR_VER}" https://github.com/verilator/verilator /build/verilator \
 && cd /build/verilator \
 && autoconf \
 && ./configure \
 && make -j "${NPROC}" \
 && make install DESTDIR=/staged \
 && find /staged -type f -perm -111 -exec strip --strip-unneeded {} + || true \
 && rm -rf /build/verilator

########## Builder: Yosys (+ yosys-slang) ##########
FROM builder-base AS build-yosys
ARG YOSYS_VER
ARG NPROC
RUN git clone --depth 1 --branch "${YOSYS_VER}" https://github.com/YosysHQ/yosys.git /build/yosys \
 && cd /build/yosys \
 && git submodule update --init --depth 1 \
 && make config-gcc \
 && make -j "${NPROC}" \
 && make install \
 && mkdir -p /staged/usr/local \
 && cp -a /usr/local/. /staged/usr/local/ \
 && rm -rf /build/yosys
RUN git clone --recursive --depth 1 https://github.com/povik/yosys-slang /build/yosys-slang \
 && cd /build/yosys-slang \
 && cmake -S . -B build \
      -DYOSYS_CONFIG=/usr/local/bin/yosys-config \
      -DCMAKE_BUILD_TYPE=Release \
 && cmake --build build -j "${NPROC}" \
 && cmake --install build --prefix /staged/usr/local --strip \
 && rm -rf /build/yosys-slang
RUN find /staged -type f -perm -111 -exec strip --strip-unneeded {} + || true

########## Builder: OpenSTA (+ CUDD + Eigen) ##########
FROM builder-base AS build-opensta
ARG OPENSTA_REPO
ARG CUDD_REPO
ARG EIGEN_REPO
ARG NPROC
RUN git clone --depth 1 "${CUDD_REPO}" /build/cudd \
 && cd /build/cudd/cudd_versions \
 && tar xfz cudd-3.0.0.tar.gz \
 && cd /build/cudd/cudd_versions/cudd-3.0.0 \
 && ./configure --prefix=/opt/deps/cudd-3.0.0 \
 && make -j "${NPROC}" install-strip
ENV CUDD_INSTALL_DIR=/opt/deps/cudd-3.0.0
RUN git clone --depth 1 "${EIGEN_REPO}" /build/eigen \
 && cmake -S /build/eigen -B /build/eigen/build \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/opt/deps/eigen \
      -DBUILD_TESTING=OFF \
 && cmake --build /build/eigen/build --parallel \
 && cmake --install /build/eigen/build --strip
RUN git clone --depth 1 "${OPENSTA_REPO}" /build/OpenSTA \
 && cmake -S /build/OpenSTA -B /build/OpenSTA/build -DCUDD_DIR=${CUDD_INSTALL_DIR} -DCMAKE_BUILD_TYPE=Release \
 && cmake --build /build/OpenSTA/build -j "${NPROC}" \
 && cmake --install /build/OpenSTA/build --prefix /opt/tools/opensta --strip \
 && rm -rf /build

########## Builder: PULP tools (bender, morty, svase) + sv2v ##########
FROM builder-base AS build-pulp
ARG NPROC
RUN set -eux; \
  curl --proto '=https' --tlsv1.2 -sSf https://pulp-platform.github.io/bender/init | bash; \
  for cand in /bender /root/.local/bin/bender /usr/local/bin/bender ./bender; do \
    if [ -f "$cand" ]; then \
      install -m 0755 "$cand" /usr/local/bin/bender; \
      break; \
    fi; \
  done; \
  command -v /usr/local/bin/bender >/dev/null
RUN set -eux; \
  curl -fsSLo /tmp/morty.tar.gz https://github.com/pulp-platform/morty/releases/download/v0.9.0/morty-ubuntu.22.04-x86_64.tar.gz; \
  tar -C /tmp -xf /tmp/morty.tar.gz; \
  install -m 0755 /tmp/morty /usr/local/bin/morty; \
  rm -rf /tmp/morty*
RUN set -eux; \
  git clone --depth 1 https://github.com/pulp-platform/svase.git /build/svase; \
  cd /build/svase; \
  sed -i 's/ -Werror//g' CMakeLists.txt; \
  make build; \
  install -m 0755 /build/svase/build/svase /usr/local/bin/svase; \
  rm -rf /build/svase
RUN set -eux; \
  mkdir -p /opt/sv2v; \
  cd /opt/sv2v; \
  wget -q https://github.com/zachjs/sv2v/releases/download/v0.0.12/sv2v-Linux.zip; \
  unzip -q sv2v-Linux.zip; \
  install -m 0755 sv2v-Linux/sv2v /usr/local/bin/sv2v; \
  rm -rf sv2v-Linux*

########## Builder: trace2power (Rust) ##########
FROM builder-base AS build-trace2power
ARG NPROC
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path \
 && source $HOME/.cargo/env \
 && git clone --depth 1 --branch 74949-glitch-power https://github.com/antmicro/trace2power.git /build/trace2power \
 && cd /build/trace2power && cargo install --path . --root /opt/tools/trace2power --locked \
 && rm -rf /build/trace2power $HOME/.cargo $HOME/.rustup

########## Builder: ASAP7 (models) ##########
FROM builder-base AS build-asap7
ARG ASAP7_REPO
RUN git clone --depth 1 "${ASAP7_REPO}" /out/asap7sc7p5t_28

########## Final stage ##########
FROM build-openroad AS base

RUN mkdir -p /opt/tools /opt/morty /opt/sv2v /proj /prog /app

# Toolchains from builders
COPY --from=build-openroad   /opt/tools/openroad /opt/tools/openroad
COPY --from=build-verilator  /staged/            /
COPY --from=build-yosys      /staged/            /
COPY --from=build-opensta    /opt/tools/opensta  /opt/tools/opensta
COPY --from=build-opensta    /opt/deps           /opt/deps
COPY --from=build-pulp       /usr/local/bin/bender /usr/local/bin/bender
COPY --from=build-pulp       /usr/local/bin/morty  /usr/local/bin/morty
COPY --from=build-pulp       /usr/local/bin/svase  /usr/local/bin/svase
COPY --from=build-pulp       /usr/local/bin/sv2v   /usr/local/bin/sv2v
COPY --from=build-trace2power /opt/tools/trace2power /opt/tools/trace2power
COPY --from=build-asap7 /out/asap7sc7p5t_28 /app/asap7sc7p5t_28
COPY --from=build-openroad /build/ORFS /prog/OpenROAD-flow-scripts
ENV MODEL_SOURCES=/app/asap7sc7p5t_28/Verilog

# PATH (OpenROAD first)
ENV PATH="/opt/tools/openroad/OpenROAD/bin:/opt/tools/opensta/app:/opt/tools/trace2power/bin:/usr/local/bin:${PATH}"


# --------- Locale ----------
RUN locale-gen en_US.UTF-8
ENV LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8

# --------- Create vscode user ----------
RUN mkdir -p /etc/sudoers.d
RUN useradd -m -s /bin/bash vscode \
 && echo "vscode ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/vscode \
 && chmod 0440 /etc/sudoers.d/vscode \
 && mkdir -p /home/vscode/.cache/uv /tmp/mplconfig \
 && chown -R vscode:vscode /home/vscode /tmp/mplconfig /prog /app
# --------- Install uv (as root) ----------
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
 && install -m 0755 /root/.local/bin/uv /usr/local/bin/uv

# --------- Create Python env & install deps (as vscode) ----------
USER vscode
WORKDIR /home/vscode
ENV PATH=/usr/local/bin:$PATH \
  UV_PYTHON_INSTALL_DIR=/home/vscode/.uv/python \
  XDG_CACHE_HOME=/home/vscode/.cache \
 LD_LIBRARY_PATH=/opt/tools/openroad/OpenROAD/lib:$LD_LIBRARY_PATH

# Create venv and auto-activate in shell sessions
RUN uv venv -n pyenv_eda --python=3.13 \
 && echo 'source /home/vscode/pyenv_eda/bin/activate' >> /home/vscode/.bashrc
ENV PATH=/home/vscode/pyenv_eda/bin:$PATH

# Core Python libs (target the venv explicitly)
RUN PY=/home/vscode/pyenv_eda/bin/python; \
    uv pip install --python="$PY" --no-cache-dir \
      cocotb==1.9.2 numpy pandas pyarrow pyyaml pytest tqdm matplotlib

# (Optional) make `python` globally visible for tools that expect it
USER root
RUN ln -sf /home/vscode/pyenv_eda/bin/python /usr/local/bin/python

# install sudo
USER root
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends sudo \
    && rm -rf /var/lib/apt/lists/* \
    && echo "vscode ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/90-vscode \
    && chmod 0440 /etc/sudoers.d/90-vscode

# nangate45 sim cells: vendored — upstream clone source was removed from GitHub; see .devcontainer/nangate45/README.md
USER vscode
COPY --chown=vscode:vscode .devcontainer/nangate45/cells.v /app/nangate/sim/cells.v

USER vscode
WORKDIR /app

########## Housekeeping ##########
RUN rm -rf /usr/share/man /usr/share/doc /usr/share/doc-base || true
