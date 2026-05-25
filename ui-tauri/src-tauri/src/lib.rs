// voice-realtime Tauri entrypoint — menubar app behavior.
//
// On macOS: ActivationPolicy::Accessory hides the dock icon. The main
// window starts hidden + decorations=false; the tray icon (built from
// `icons/32x32.png`) toggles it on click. When shown, the window is
// positioned near the tray icon so it feels like a popover.

use std::fs::OpenOptions;
use std::process::{Command, Stdio};

use tauri::{
    image::Image,
    menu::{Menu, MenuItem},
    tray::{MouseButton, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager,
};

// #[cfg(target_os = "macos")]
// use tauri::ActivationPolicy;

// 128x128 chosen over 32x32 because macOS menubar is ~22pt = 44px @2x
// Retina; a 32px source ends up rendered at half size (barely visible).
// The 128px source downscales cleanly to menubar size.
const TRAY_ICON_BYTES: &[u8] = include_bytes!("../icons/128x128.png");

/// Hardcoded path to the uv-managed CLI venv shim. Resolved at build time
/// from the project layout: ../voice-realtime/.venv/bin/voice-realtime relative
/// to ui-tauri/src-tauri. Adjust if the project is relocated.
const CLI_BIN: &str = "/Users/stephanedufresne/OBSIDIAN/PROJETS DEV/voice-realtime/.venv/bin/voice-realtime";

/// Spawn `voice-realtime talk --ui --persona <slug>` as a detached background
/// process. Stdout/stderr are swallowed — the UI observes session state
/// through the WS control server, not the subprocess streams. Returns Ok as
/// soon as the spawn succeeds (does not wait for the CLI to be ready).
const CLI_LOG: &str = "/tmp/voice-realtime-cli.log";

#[tauri::command]
#[allow(clippy::too_many_arguments)]
async fn spawn_cli_session(
    persona: String,
    max_minutes: Option<f64>,
    // Sprint 4 — forward persona-driven flags so the UI can launch a session
    // pre-configured (project hint, cli_context, rolling toggles). None = let
    // the CLI fall back to its own defaults (which include the persona's
    // frontmatter, so passing them again here is redundant if you trust
    // persona load — but explicit > implicit when scripting).
    project: Option<String>,
    cli_context: Option<bool>,
    rolling_recap: Option<bool>,
    rolling_terminal: Option<bool>,
) -> Result<(), String> {
    let max = max_minutes.unwrap_or(30.0);
    let max_str = format!("{}", max);

    // Capture child stdout+stderr to a known file so we can read failures
    // back to the user instead of swallowing them. Truncates on each launch.
    let log = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(CLI_LOG)
        .map_err(|e| format!("cannot open log {}: {}", CLI_LOG, e))?;
    let log_err = log.try_clone()
        .map_err(|e| format!("cannot clone log handle: {}", e))?;

    let mut args: Vec<String> = vec![
        "talk".into(),
        "--ui".into(),
        "--persona".into(),
        persona.clone(),
        "--max-minutes".into(),
        max_str,
        "--clean-terminal".into(),
    ];
    if let Some(p) = project.as_ref().filter(|s| !s.trim().is_empty()) {
        args.push("--project".into());
        args.push(p.clone());
    }
    if let Some(true) = cli_context {
        args.push("--cli-context".into());
    }
    // rolling_recap defaults ON in the CLI, expose explicit opt-out flag.
    if let Some(false) = rolling_recap {
        args.push("--no-rolling-recap".into());
    }
    if let Some(true) = rolling_terminal {
        args.push("--rolling-terminal".into());
    }

    let result = Command::new(CLI_BIN)
        .args(&args)
        // Inherit the user's full env (HOME, PATH, GOOGLE creds, etc.) —
        // the CLI loads config from $HOME/.claude/voice-realtime.env and
        // sounddevice needs DYLD_LIBRARY_PATH on macOS.
        .stdin(Stdio::null())
        .stdout(Stdio::from(log))
        .stderr(Stdio::from(log_err))
        .spawn();
    match result {
        Ok(_child) => Ok(()),
        Err(err) => Err(format!(
            "failed to spawn CLI ({}): {} — check {}",
            CLI_BIN, err, CLI_LOG,
        )),
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_fs::init())
        .setup(|app| {
            // ActivationPolicy::Accessory disabled while debugging tray
            // visibility on macOS 15.5 — Sequoia + non-bundled dev binary +
            // Accessory policy = tray icon installs silently but doesn't
            // render. Restore once tray works end-to-end.
            // #[cfg(target_os = "macos")]
            // {
            //     app.set_activation_policy(ActivationPolicy::Accessory);
            // }

            // Tray context menu — accessible via right-click.
            let toggle_i = MenuItem::with_id(app, "toggle", "Show / Hide", true, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "Quit", true, Some("Cmd+Q"))?;
            let menu = Menu::with_items(app, &[&toggle_i, &quit_i])?;

            let tray_icon = Image::from_bytes(TRAY_ICON_BYTES)?;
            // icon_as_template DISABLED — the bundled 32x32.png is a full-color
            // Tauri logo, not an alpha-only template. macOS would render nothing
            // (or a blank slot) when template mode is on with a colored image.
            // For a proper monochrome menubar icon, replace 32x32.png with an
            // alpha-only PNG and re-enable .icon_as_template(true).
            let tray_build = TrayIconBuilder::with_id("main-tray")
                .icon(tray_icon)
                .tooltip("voice-realtime — click to toggle")
                .menu(&menu)
                .show_menu_on_left_click(false) // left click = popover toggle
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "toggle" => toggle_window(app),
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: tauri::tray::MouseButtonState::Up,
                        ..
                    } = event
                    {
                        toggle_window(tray.app_handle());
                    }
                })
                .build(app);
            match tray_build {
                Ok(_tray) => eprintln!("[voice-realtime] tray icon installed"),
                Err(err) => eprintln!("[voice-realtime] FAILED to install tray icon: {err}"),
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![spawn_cli_session])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn toggle_window(app: &AppHandle) {
    let Some(window) = app.get_webview_window("main") else {
        return;
    };
    let visible = window.is_visible().unwrap_or(false);
    if visible {
        let _ = window.hide();
    } else {
        let _ = window.show();
        let _ = window.set_focus();
        // Best-effort: center under the menubar. Tauri 2 doesn't expose tray
        // pixel coords cross-platform yet, so we anchor to the screen's top
        // edge and let the user drag the window if they want a different
        // position. The window-state plugin (future) can persist that.
        if let Ok(Some(monitor)) = window.current_monitor() {
            let screen = monitor.size();
            let scale = monitor.scale_factor();
            let win_w = (480.0 * scale) as u32;
            let x = (screen.width as i32 - win_w as i32) / 2;
            let _ = window.set_position(tauri::PhysicalPosition { x, y: 32 });
        }
    }
}
