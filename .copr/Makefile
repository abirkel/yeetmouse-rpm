MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
SRCDIR := $(abspath $(MAKEFILE_DIR)/../specs)

srpm:
	mkdir -p "$(outdir)"
	dnf -y install rpm-build
	case "$(spec)" in \
	  *kmod-yeetmouse.spec) dnf -y install kmodtool kernel-devel ;; \
	esac
	rpmbuild -bs --define "_srcrpmdir $(outdir)" --define "_sourcedir $(SRCDIR)" "$(spec)"

