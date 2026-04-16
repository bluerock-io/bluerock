/*
 * Copyright (C) 2026 BlueRock Security, Inc.
 * All rights reserved.
 */

use std::cell::RefCell;
use std::ffi::{CStr, CString, c_char, c_int};
use std::fs::OpenOptions;
use std::io::Write;
use std::path::PathBuf;
use std::sync::OnceLock;
use thiserror::Error;

#[derive(Debug, Error)]
enum Error {
    #[error("Invalid arguments: {0}")]
    InvalidArgs(#[from] serde_json::Error),
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
    #[error("Not initialized")]
    Uninitialized,
}

#[allow(clippy::enum_variant_names)]
#[repr(C)]
pub enum AcousticStatus {
    AcousticSuccess = 0,
    AcousticUninitialized = 1,
    AcousticInvalidArgs = 2,
    AcousticGyroFailure = 3,
    AcousticIoError = 4,
    AcousticEnvError = 5,
}

impl AcousticStatus {
    fn from_error(e: &Error) -> Self {
        match e {
            Error::InvalidArgs(..) => Self::AcousticInvalidArgs,
            Error::Io(..) => Self::AcousticIoError,
            Error::Uninitialized => Self::AcousticUninitialized,
        }
    }
}

static SENSOR_CONFIG: OnceLock<serde_json::Value> = OnceLock::new();

fn load_sensor_config(metadata_ptr: *const c_char) {
    let config = (|| -> Option<serde_json::Value> {
        let metadata_str = unsafe { CStr::from_ptr(metadata_ptr) }.to_str().ok()?;
        let metadata: serde_json::Value = serde_json::from_str(metadata_str).ok()?;
        let config_dir = metadata.get("config_dir")?.as_str()?;
        let path = PathBuf::from(config_dir).join("bluerock-oss.json");
        let contents = std::fs::read_to_string(&path).ok()?;
        serde_json::from_str(&contents).ok()
    })()
    .unwrap_or_else(|| {
        serde_json::json!({
            "enable": true,
            "imports": {"enable": true, "fileslist": true},
            "mcp": true
        })
    });
    let _ = SENSOR_CONFIG.set(config);
}

enum Context {
    Empty,
    Error(CString),
    Config(CString),
    #[allow(dead_code)]
    Modification(CString),
}

impl Context {
    fn config(v: serde_json::Value) -> Self {
        Context::Config(CString::new(v.to_string()).unwrap())
    }
}

thread_local! {
    static CONTEXT: RefCell<Context> = const { RefCell::new(Context::Empty) };
    static GENERATION: RefCell<u32> = const { RefCell::new(0) };
}

impl From<()> for Context {
    fn from(_: ()) -> Self {
        Context::Empty
    }
}

impl From<Error> for Context {
    fn from(e: Error) -> Self {
        Context::Error(CString::new(e.to_string()).unwrap())
    }
}

fn stash_into_context<T: Into<Context>>(result: Result<T, Error>) -> AcousticStatus {
    match result {
        Ok(v) => {
            CONTEXT.replace(v.into());
            AcousticStatus::AcousticSuccess
        }
        Err(e) => {
            let status = AcousticStatus::from_error(&e);
            CONTEXT.replace(e.into());
            status
        }
    }
}

fn stash_return_value_into_context<T: Into<Context>, F: FnOnce() -> Result<T, Error>>(
    f: F,
) -> AcousticStatus {
    stash_into_context(f())
}

/// Linux: kernel thread ID via gettid(). Behaves exactly as the
/// inline call in main; just wrapped so the macOS branch below has
/// somewhere to live.
#[cfg(target_os = "linux")]
fn get_thread_id() -> i32 {
    rustix::thread::gettid().as_raw_nonzero().get()
}

/// macOS: Mach thread ID via pthread_threadid_np. Truncated to i32
/// to match the Linux signature — the value only feeds into the
/// per-PID/TID event-spool filename, where collisions just merge two
/// threads into the same file (same as Linux today).
#[cfg(target_os = "macos")]
fn get_thread_id() -> i32 {
    let mut tid: u64 = 0;
    // SAFETY: pthread_threadid_np writes the calling thread's ID to
    // the out-pointer. The pointer is to a stack local, valid for the
    // duration of the call. A null-thread argument means "current
    // thread", which is what we want.
    unsafe { libc::pthread_threadid_np(0, &mut tid) };
    tid as i32
}

fn event_file_path(dir: &str, pid: u32, tid: i32, generation: u32) -> PathBuf {
    PathBuf::from(format!(
        "{}/python-{}-{}.{}.ndjson",
        dir, pid, tid, generation
    ))
}

fn rotate_event_spool(dir: &str) {
    const MAX_SPOOL_SIZE: u64 = 10 * 1024 * 1024;

    let entries = match std::fs::read_dir(dir) {
        Ok(e) => e,
        Err(_) => return,
    };

    let mut files: Vec<(std::time::SystemTime, u64, PathBuf)> = entries
        .filter_map(|e| e.ok()) // read_dir() returns an iterator of Results.
        .filter(|e| {
            e.path()
                .extension()
                .map(|ext| ext == "ndjson")
                .unwrap_or(false)
        })
        .filter_map(|e| {
            // stat() each file to get the size and mtime.
            let meta = e.metadata().ok()?;
            let mtime = meta.modified().ok()?;
            Some((mtime, meta.len(), e.path()))
        })
        .collect();

    let total: u64 = files.iter().map(|(_, sz, _)| sz).sum();
    if total <= MAX_SPOOL_SIZE {
        return;
    }

    // Delete files in order of increasing mtime until we reach MAX_SPOOL_SIZE.
    files.sort_by_key(|(mtime, _, _)| *mtime);
    let mut remaining = total;
    for (_, sz, path) in files {
        if remaining <= MAX_SPOOL_SIZE {
            break;
        }
        let _ = std::fs::remove_file(&path);
        remaining -= sz;
    }
}

/// Enables tracing and logging to stderr.
///
/// # Safety
/// No pointer arguments. Always safe to call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn acoustic_tracing_stderr() -> c_int {
    0
}

/// Enables tracing and logging to a file.
///
/// # Safety
/// `_path` must be a valid null-terminated C string or null. Stub — ignores the argument.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn acoustic_tracing_file(_path: *const c_char) -> c_int {
    0
}

/// Emits a log message through the tracing infrastructure.
///
/// # Safety
/// `_msg` must be a valid null-terminated C string or null. Stub — ignores the argument.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn acoustic_tracing_log(_level: c_int, _msg: *const c_char) -> c_int {
    0
}

/// Initializes libacoustic.
///
/// # Safety
/// Both pointers must be valid null-terminated C strings. Stub — ignores arguments.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn acoustic_init(
    _socket_path_ptr: *const c_char,
    metadata_ptr: *const c_char,
) -> c_int {
    load_sensor_config(metadata_ptr);
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".to_string());
    let dir = format!("{}/.bluerock/event-spool", home);
    let _ = std::fs::create_dir_all(&dir);
    rotate_event_spool(&dir);
    0
}

/// Initializes libacoustic with fork-safe mode.
///
/// # Safety
/// Both pointers must be valid null-terminated C strings. Stub — ignores arguments.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn acoustic_init_forksafe(
    _socket_path_ptr: *const c_char,
    metadata_ptr: *const c_char,
) -> c_int {
    load_sensor_config(metadata_ptr);
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".to_string());
    let dir = format!("{}/.bluerock/event-spool", home);
    let _ = std::fs::create_dir_all(&dir);
    rotate_event_spool(&dir);
    0
}

/// Re-initializes libacoustic (e.g., after fork()).
///
/// # Safety
/// No pointer arguments. Always safe to call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn acoustic_reset() -> c_int {
    0
}

/// Handles acoustic messages on the current thread (blocking).
///
/// # Safety
/// Both function pointers must be valid. Stub — ignores both callbacks.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn acoustic_run(
    _handle_config_update_fn: unsafe extern "C" fn(*const u8, usize) -> c_int,
    _handle_policy_revoked_fn: unsafe extern "C" fn(),
) -> c_int {
    0
}

/// Handles pending acoustic messages on the current thread (non-blocking).
///
/// # Safety
/// Both function pointers must be valid. Stub — ignores both callbacks.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn acoustic_poll(
    _handle_config_update_fn: unsafe extern "C" fn(*const u8, usize) -> c_int,
    _handle_policy_revoked_fn: unsafe extern "C" fn(),
) -> c_int {
    0
}

/// Evaluates a single query/event against the current rego engine state.
///
/// # Safety
/// `input_json_ptr` must point to a valid UTF-8 buffer of `input_json_sz` bytes.
/// `out_block_event` must be a valid pointer to a writable `c_int`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn acoustic_event(
    input_json_ptr: *const c_char,
    input_json_sz: usize,
    out_block_event: *mut c_int,
) -> c_int {
    stash_return_value_into_context(|| {
        let slice =
            unsafe { std::slice::from_raw_parts(input_json_ptr as *const u8, input_json_sz) };

        let value = serde_json::from_slice::<serde_json::Value>(slice)?;

        // Log event as NDJSON to a per-PID/TID file in ~/.bluerock/event-spool/.
        let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".to_string());
        let dir = format!("{}/.bluerock/event-spool", home);
        std::fs::create_dir_all(&dir)?;
        let pid = std::process::id();
        let tid = get_thread_id();
        let path = GENERATION.with_borrow_mut(|generation| {
            let path = event_file_path(&dir, pid, tid, *generation);
            if let Ok(meta) = std::fs::metadata(&path)
                && meta.len() >= 1024 * 1024
            {
                *generation += 1;
                rotate_event_spool(&dir);
            }
            event_file_path(&dir, pid, tid, *generation)
        });
        let mut file = OpenOptions::new().create(true).append(true).open(&path)?;
        let ts = chrono::Utc::now().to_rfc3339();
        let envelope = serde_json::json!({"ts": ts, "event": value});
        serde_json::to_writer(&mut file, &envelope)?;
        file.write_all(b"\n")?;

        unsafe { out_block_event.write(0) };
        Ok(())
    }) as c_int
}

/// Retrieves the current sensor ID.
///
/// # Safety
/// `out_sensor_id` must be a valid pointer to a writable `u64`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn acoustic_get_sensor_id(out_sensor_id: *mut u64) -> c_int {
    unsafe { out_sensor_id.write(1) };
    0
}

/// Retrieves the current sensor config and stores it into context.
///
/// # Safety
/// No pointer arguments. Always safe to call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn acoustic_get_sensor_config() -> c_int {
    stash_return_value_into_context(|| {
        let config = SENSOR_CONFIG.get().ok_or(Error::Uninitialized)?;
        Ok(Context::config(config.clone()))
    }) as c_int
}

/// Returns the error message that was encountered by the last libacoustic function.
///
/// # Safety
/// `out_ptr` must be a valid pointer to a writable `*const c_char`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn acoustic_last_error_msg(out_ptr: *mut *const c_char) {
    CONTEXT.with(|ctx| {
        let ptr = match &*ctx.borrow() {
            Context::Error(e) => e.as_ptr(),
            _ => std::ptr::null(),
        };
        unsafe { out_ptr.write(ptr) };
    });
}

/// Returns the last retrieved sensor config.
///
/// # Safety
/// `out_ptr` must be a valid pointer to a writable `*const c_char`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn acoustic_last_sensor_config(out_ptr: *mut *const c_char) {
    CONTEXT.with(|ctx| {
        let ptr = match &*ctx.borrow() {
            Context::Config(c) => c.as_ptr(),
            _ => std::ptr::null(),
        };
        unsafe { out_ptr.write(ptr) };
    });
}

/// Returns the last JSON blob for modify remediations.
///
/// # Safety
/// `out_ptr` must be a valid pointer to a writable `*const c_char`.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn acoustic_last_modification(out_ptr: *mut *const c_char) {
    CONTEXT.with(|ctx| {
        let ptr = match &*ctx.borrow() {
            Context::Modification(m) => m.as_ptr(),
            _ => std::ptr::null(),
        };
        unsafe { out_ptr.write(ptr) };
    });
}
