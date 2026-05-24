// voice-realtime Tauri entrypoint — menubar app behavior.
//
// On macOS: ActivationPolicy::Accessory hides the dock icon. The main
// window starts hidden + decorations=false; the tray icon (built from
// `icons/32x32.png`) toggles it on click. When shown, the window is
// positioned near the tray icon so it feels like a popover.

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
#[tauri::command]
async fn spawn_cli_session(persona: String, max_minutes: Option<f64>) -> Result<(), String> {
    let max = max_minutes.unwrap_or(30.0);
    let max_str = format!("{}", max);
    let result = Command::new(CLI_BIN)
        .args([
            "talk",
            "--ui",
            "--persona",
            &persona,
            "--max-minutes",
            &max_str,
            "--clean-terminal",
        ])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn();
    match result {
        Ok(_child) => Ok(()),
        Err(err) => Err(format!("failed to spawn CLI ({}): {}", CLI_BIN, err)),
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
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
