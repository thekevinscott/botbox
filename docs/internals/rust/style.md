# Rust — style

## Reading vocabulary

| Syntax | Meaning |
|---|---|
| `fn foo(x: T) -> R` | function; `->` is return type |
| `use path::to::thing;` | import |
| `let x = ...` | immutable binding (like JS `const`) |
| `let mut x = ...` | mutable binding (like JS `let`) |
| `mut` | makes things mutable; required to mutate |
| `Vec<T>` | growable list (Python `list[T]`) |
| `Option<T>` | `Some(t)` or `None` (Python `Optional[T]`) |
| `Result<T, E>` | `Ok(t)` or `Err(e)` — failure made explicit |
| `()` | the *unit type* (Python `None`-ish; TS `void`) |
| `&T` | borrowed read-only reference |
| `&mut T` | exclusive mutable reference |
| `String` / `&str` | owned / borrowed string |
| `PathBuf` / `&Path` | owned / borrowed path |
| `Vec<T>` / `&[T]` | owned / borrowed slice |
| `?` | propagate error: if `Err`, return; if `Ok(v)`, unwrap |
| `\|args\| body` | closure (lambda) |
| `\|\|` | closure with no args |
| `name!(...)` | macro invocation (compile-time code generation) |
| `#[derive(Foo)]` | generates `impl Foo for ThisType` at compile time |
| `#[cfg(test)]` | only compile when running tests |
| `pub` | public visibility |
| `mod foo;` | declare a module |
| `Self` | "this type" |
| `self`, `&self`, `&mut self` | method receivers (instance methods) |

### Key foundational concepts

- **No GC, no manual free.** Compiler inserts `drop()` at scope ends. Deterministic, zero runtime overhead.
- **Ownership.** Every value has exactly one owner. Moves transfer ownership; borrows (`&T`) loan a view.
- **Borrow checker.** At compile time, proves no use-after-free and no data races. Refuses to compile if it can't prove.
- **No inheritance.** Structs can't extend. Code reuse is via **traits** (interfaces with optional default methods).
- **Expressions, not statements.** `if/else`, blocks, `match` all evaluate to values. The last expression in a block (no `;`) is the block's value — including function returns.
- **Trait methods require the trait in scope.** `use std::io::BufRead;` to call `.lines()` on a reader. The compiler errors with "no method named X" when you forget.

---

## Memory model in one paragraph

Variables own their values. Values are freed at the closing brace of their owner's scope (compiler inserts `drop()` — deterministic, no GC). You can transfer ownership by *moving* (`let y = x;` makes `y` the owner and `x` unusable), or you can loan a *borrow* via `&` (cheap, compile-time-checked, no ownership transfer). `&T` is read-only; `&mut T` is exclusive read-write. The borrow checker proves at compile time that no borrow outlives its owner and no mutable borrow coexists with any other borrow. Multiple owners require opt-in reference counting (`Rc<T>` for single-threaded, `Arc<T>` for shared across threads).

---

## Idiomatic patterns (what GOOD looks like)

### Error handling
- Helper functions return precise error types: `io::Result<T>`, `Result<T, MyNewProductError>`.
- Binary `main` returns `anyhow::Result<()>`.
- Use `?` for propagation; `.with_context(|| format!("...{var}"))?` to add context at each layer.
- For libraries, define typed errors with `thiserror`. **Don't use `anyhow` in library APIs.**

### Borrowing
- **Default to `&T`.** Reach for ownership only when downstream actually needs it.
- Functions take `&str` not `String` for parameters (callers can pass either).
- Functions take `&[T]` not `Vec<T>` for slice-like inputs.
- "Pick the weakest access you need."

### Construction
- `Type::new()` for the simplest case.
- `Type::with_<thing>(...)` for variants taking config.
- `Type::from(other)` for conversions (paired with `From` trait).
- `Type::try_new()` / `try_from` for fallible variants (returns `Result`).
- For many optional fields: builder pattern. `Foo::builder().with_x(1).with_y(true).build()`.

### Iteration
- `for x in &collection` — normal. Borrowing.
- `for x in collection` — consumes. Used when downstream needs ownership.
- `for x in &mut collection` — mutable borrow.
- Iterator chains are idiomatic: `vec.iter().filter(...).map(...).collect::<Vec<_>>()`.

Testing patterns are in [testing.md](testing.md).
