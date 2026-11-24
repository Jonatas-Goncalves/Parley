%global appid io.github.jonatasgoncalves.Parley

%if 0%{?sle_version}
%define pygobject python311-gobject
%define pygobject_gdk python311-gobject-Gdk
%define python_base python311-base
%else
%define pygobject python313-gobject
%define pygobject_gdk python313-gobject-Gdk
%define python_base python313-base
%endif

Name:           parley
Version:        1.0.0
Release:        1
Summary:        Local voice-first language tutor
License:        MIT
Group:          Productivity/Education
URL:            https://github.com/Jonatas-Goncalves/Parley
Source0:        parley-%{version}.tar.gz
BuildArch:      noarch
Requires:       python3 >= 3.11
Requires:       %{python_base}
Requires:       %{pygobject}
Requires:       %{pygobject_gdk}
Requires:       gtk4
Requires:       typelib-1_0-Gtk-4_0
Requires:       libportaudio2
Requires:       libsndfile1
Requires:       ffmpeg
Requires:       ca-certificates
Requires:       google-noto-sans-cjk-fonts
Recommends:     ollama

%description
Parley is a desktop language tutor that runs entirely on your computer. It
combines a local language model, speech recognition and speech synthesis for
Portuguese, English, Spanish, French, Italian, Japanese, Korean and Mandarin
Chinese.

The interface is built with GTK 4. Voice Practice offers 19 role-play scenarios,
Pronunciation compares your reading with a generated phrase, Spoken Stories
plays public-domain recordings, and Complete the Sentence trains listening and
spelling.

No account, cloud service or telemetry is used.

%prep
%setup -q

%build

%install
bash packaging/linux/stage-app.sh . %{buildroot}/usr

%post
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi

%postun
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi

%files
%license LICENSE
%doc README.md
%{_bindir}/parley
%{_prefix}/lib/parley
%{_datadir}/applications/%{appid}.desktop
%{_datadir}/metainfo/%{appid}.metainfo.xml
%{_datadir}/icons/hicolor/*/apps/%{appid}.png
%{_datadir}/doc/parley

%changelog
* Tue Nov 17 2026 Parley contributors <parley@users.noreply.github.com> - 0.3.1-1
- Fix pronunciation phrase length, punctuation and hyphenated words.
- Stop Voice Practice from repeating questions already answered.
- Require or bundle Noto Sans CJK and translate the CJK home buttons.
- Add llama.cpp and offline Termux support to the Android app.
* Mon Nov 16 2026 Parley contributors <parley@users.noreply.github.com> - 0.3.0-1
- Add conversation scoring, per-language progress and a guided level test.
- Follow the system theme, confirm model downloads and allow voice removal.
- Fix audio replay, Back navigation after a session and CJK font detection.
* Mon Nov 16 2026 Parley contributors <parley@users.noreply.github.com> - 0.2.0-1
- First GTK 4 release with Italian, spoken stories and on-demand audio.
