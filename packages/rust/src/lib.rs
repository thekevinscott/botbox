use clap::Parser;

pub mod entrypoint;

#[derive(Parser, Debug)]
#[command(
    name = "mynewproduct",
    version,
    about,
    long_about = None,
)]
pub struct Cli {}

pub fn run<I, T>(args: I) -> anyhow::Result<i32>
where
    I: IntoIterator<Item = T>,
    T: Into<std::ffi::OsString> + Clone,
{
    let _cli = Cli::try_parse_from(args)?;
    Ok(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn no_args_returns_ok_zero() {
        assert_eq!(run(["mynewproduct"]).unwrap(), 0);
    }

    #[test]
    fn unknown_flag_errors() {
        assert!(run(["mynewproduct", "--bogus"]).is_err());
    }

    #[test]
    fn help_flag_returns_clap_display_help() {
        let err = run(["mynewproduct", "--help"]).expect_err("--help should bubble");
        let clap_err = err
            .downcast_ref::<clap::Error>()
            .expect("error should be a clap::Error");
        assert_eq!(clap_err.kind(), clap::error::ErrorKind::DisplayHelp);
    }

    #[test]
    fn version_flag_returns_clap_display_version() {
        let err = run(["mynewproduct", "--version"]).expect_err("--version should bubble");
        let clap_err = err
            .downcast_ref::<clap::Error>()
            .expect("error should be a clap::Error");
        assert_eq!(clap_err.kind(), clap::error::ErrorKind::DisplayVersion);
    }
}
