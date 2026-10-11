use std::process::ExitCode;

// `cargo test` swaps in its own `main`, so no test can run this; it only reads argv. The decisions
// live in `report`.
#[cfg(not(test))]
pub fn main() -> ExitCode {
    report(crate::run(std::env::args_os()))
}

// `print` plus `exit_code` is `clap::Error::exit` without the `process::exit`, so tests can call it.
fn report(result: anyhow::Result<i32>) -> ExitCode {
    match result {
        Ok(code) => ExitCode::from(code as u8),
        Err(err) => match err.downcast_ref::<clap::Error>() {
            Some(clap_err) => {
                let _ = clap_err.print();
                ExitCode::from(clap_err.exit_code() as u8)
            }
            None => {
                eprintln!("error: {err}");
                ExitCode::from(1)
            }
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_success_code_becomes_that_exit_code() {
        assert_eq!(report(Ok(0)), ExitCode::from(0));
        assert_eq!(report(Ok(3)), ExitCode::from(3));
    }

    #[test]
    fn a_plain_failure_exits_one() {
        assert_eq!(report(Err(anyhow::anyhow!("boom"))), ExitCode::from(1));
    }

    #[test]
    fn a_usage_mistake_exits_two() {
        let err = clap::Error::new(clap::error::ErrorKind::UnknownArgument);
        assert_eq!(report(Err(err.into())), ExitCode::from(2));
    }

    #[test]
    fn help_exits_zero() {
        let err = clap::Error::new(clap::error::ErrorKind::DisplayHelp);
        assert_eq!(report(Err(err.into())), ExitCode::from(0));
    }
}
