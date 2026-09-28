//! Opt-in evidence file for captured Git read commands. Stdout stays unchanged.

use serde::Serialize;
use std::fs::OpenOptions;
use std::io::{BufWriter, Write};
use std::path::Path;
use std::process::Command;

use crate::core::stream::CaptureResult;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct Comparison<'a> {
    original: &'a str,
    git_args: Vec<String>,
}

#[derive(Serialize)]
struct Evidence<'a> {
    version: u8,
    #[serde(skip_serializing_if = "Option::is_none")]
    comparison: Option<Comparison<'a>>,
}

pub fn export(result: &CaptureResult, command: &Command) {
    let Some(path) = std::env::var_os("RTK_AIB_EXPORT_PATH").filter(|path| !path.is_empty()) else {
        return;
    };
    // The caller owns the directory and supplies a fresh per-call path. Evidence
    // failure must not change Git stdout, stderr or exit status.
    let _ = write_evidence(Path::new(&path), result, command);
}

fn write_evidence(path: &Path, result: &CaptureResult, command: &Command) -> anyhow::Result<()> {
    let file = OpenOptions::new().write(true).create_new(true).open(path)?;
    let mut writer = BufWriter::new(file);
    let evidence = Evidence {
        version: 1,
        comparison: result.success().then(|| Comparison {
            original: &result.stdout,
            git_args: command
                .get_args()
                .map(|arg| arg.to_string_lossy().into_owned())
                .collect(),
        }),
    };
    serde_json::to_writer(&mut writer, &evidence)?;
    writeln!(writer)?;
    writer.flush()?;
    Ok(())
}
