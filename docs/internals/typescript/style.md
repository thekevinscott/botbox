# TypeScript — style

## What good TS code looks like

Positive checklist for reviewing agent output:

- **Types**: every public function, method, and exported value has explicit types. `unknown` at boundaries, narrowed before use. Generic params constrained to the narrowest workable shape.
- **`satisfies` over `as`**: literal types stay literal; checks happen at definition.
- **Awaited promises**: every `Promise` is either `await`ed, returned, or explicitly marked `void p` for fire-and-forget. `@typescript-eslint/no-floating-promises` enforces this.
- **Explicit barrels**: `export { Name } from './file'` at each level; the public surface is intentional.
- **Subpath types**: each conditional entry in `exports` has its own `"types"`.
- **`sideEffects: false`** on side-effect-free packages; otherwise an explicit allowlist.
- **Colocated tests**: `src/foo.ts` + `src/foo.test.ts`. Integration tests at repo root consume the built artifact.
- **Factory injection** for testable classes: dependencies passed via the constructor; tests pass fakes.
- **Modern idioms**: `structuredClone` for deep copy, spread for object merge, `for ... of` for iteration, string-literal unions over runtime enums, `const` by default.
- **Real privacy where it matters**: `#private` or `_field` + `@hidden` consistently within a class.
- **`tsc --noEmit`, eslint, prettier, vitest** all green before review.

---

## Type-system idiom reference

| Pattern | Meaning |
|---|---|
| `T extends U` (in `extends` clause) | Generic constraint: `T` must be assignable to `U` |
| `T extends U ? A : B` | Conditional type |
| `keyof T` | Union of `T`'s keys (as string-literal types) |
| `T[K]` | Index access — the type of `T`'s `K` property |
| `Partial<T>` | All fields optional |
| `Required<T>` | All fields required (strip `?`) |
| `Readonly<T>` | All fields readonly |
| `Pick<T, K>` | Subset by keys |
| `Omit<T, K>` | Complement of `Pick` |
| `Record<K, V>` | Object with keys of `K`, values of `V` |
| `ReturnType<F>` | Return type of function-type `F` |
| `Parameters<F>` | Tuple of param types |
| `Awaited<P>` | Unwrap `Promise<T>` to `T` |
| `as const` | Treat literal as its narrowest literal type |
| `satisfies T` | Type-check against `T` *without* widening — preserves the literal type |
| `infer X` (in conditional type) | Bind a name to an inferred position |
| `T & U` | Intersection type |
| `T \| U` | Union type |
| `unknown` | "Anything, but must be narrowed before use" (the safe `any`) |
| `never` | "Cannot happen" — return type of throwing/looping-forever functions |
| `void` | Function return that's discarded (different from `undefined` in callback positions) |
| `#field` | Real private (runtime-enforced) class field |
| `readonly field: T` | TS-only immutability in class/object types |

**`satisfies` is the modern alternative to `as`.** It checks assignability without widening:

```ts
// `as` widens — `colors.red` is now `string`, not `'#ff0000'`
const colors = { red: '#ff0000', blue: '#0000ff' } as { [k: string]: string };

// `satisfies` checks but doesn't widen — `colors.red` stays `'#ff0000'`
const colors = { red: '#ff0000', blue: '#0000ff' } satisfies Record<string, string>;
```

`satisfies` is type-checking (verify), `as` is type-asserting (trust me). Prefer `satisfies` for literal-preserving checks.
