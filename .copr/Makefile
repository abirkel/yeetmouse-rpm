# COPR's default SCM build method ("rpkg") generates the SRPM in a lightweight
# environment that is NOT the full mock chroot and has no documented way to
# install packages during that step. kmod-yeetmouse.spec evaluates
# `%(rpm -q kernel-devel ...)` and `%{expand:%(kmodtool ...)}` directly at
# spec-PARSE time (before %prep), so `rpkg` fails there with
# "kmodtool: command not found".
#
# `make_srpm` runs this Makefile's `srpm` target as root inside a real mock
# chroot with network access (confirmed against COPR's own docs:
# https://docs.copr.fedorainfracloud.org/user_documentation.html, "make srpm"
# section), so it is the correct, documented place to install
# kmodtool/kernel-devel before generating the SRPM -- not a workaround. This
# is the same pattern akmods/negativo17/RPM Fusion kmod COPR projects use for
# the identical problem.
#
# Copr invokes this target as:
#   make -f .copr/Makefile srpm outdir="<outdir>" spec="<spec_path>"
# `spec` is whatever is set in the SCM package's "Spec File" field, so the
# same target serves both kmod-yeetmouse.spec and yeetmouse.spec.
#
# `$(PWD)` at invocation time is NOT guaranteed to be the repo root -- Copr's
# `make -f <path>/.copr/Makefile` does not itself cd anywhere, and relying on
# invocation cwd is an unverified implementation detail, not a documented
# contract. Anchor _sourcedir off this Makefile's own location instead, which
# is correct regardless of invocation cwd (senior-SDE review finding,
# e91b087c).
#
# All non-Source0 sources (config.h, yeetmouse.service,
# yeetmouse-preset.conf, yeetmouse-sysusers.conf, yeetmouse.conf) live at the
# REPO ROOT, not under specs/ -- confirmed by a real failed test build
# (Copr build 11078777: "Bad file: .../specs/config.h: No such file or
# directory"). _sourcedir must point at the repo root, which is the parent
# of the directory this Makefile lives in (.copr/..).
#
# Set each SCM package's build method to `make_srpm` for this to take effect
# (copr-cli add-package-scm / edit-package-scm --method make_srpm).

MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
SRCDIR := $(abspath $(MAKEFILE_DIR)/..)

srpm:
	mkdir -p "$(outdir)"
	dnf -y install rpm-build
	case "$(spec)" in \
	  *kmod-yeetmouse.spec) dnf -y install kmodtool kernel-devel ;; \
	esac
	rpmbuild -bs --define "_srcrpmdir $(outdir)" --define "_sourcedir $(SRCDIR)" "$(spec)"
