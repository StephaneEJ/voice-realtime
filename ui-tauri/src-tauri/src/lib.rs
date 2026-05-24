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

#[cfg(target_os = "macos")]
use tauri::ActivationPolicy;

const TRAY_ICON_BYTES: &[u8] = include_bytes!("../icons/32x32.png");

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
            #[cfg(target_os = "macos")]
            {
                // Accessory = no dock icon, no menu bar of the app itself.
                // We live in the system menubar only.
                app.set_activation_policy(ActivationPolicy::Accessory);
            }

            // Tray context menu — accessible via right-click.
            let toggle_i = MenuItem::with_id(app, "toggle", "Show / Hide", true, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "Quit", true, Some("Cmd+Q"))?;
            let menu = Menu::with_items(app, &[&toggle_i, &quit_i])?;

            let tray_icon = Image::from_bytes(TRAY_ICON_BYTES)?;
            let _tray = TrayIconBuilder::with_id("main-tray")
                .icon(tray_icon)
                .icon_as_template(true) // macOS: render in menubar tint
                .menu(&menu)
                .show_menu_on_left_click(false) // left click = popover toggle
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "toggle" => toggle_window(app),
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    // Left click on tray icon → toggle popover near the icon.
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: tauri::tray::MouseButtonState::Up,
                        ..
                    } = event
                    {
                        toggle_window(tray.app_handle());
                    }
                })
                .build(app)?;

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
