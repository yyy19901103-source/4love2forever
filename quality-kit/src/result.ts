/**
 * 特徴1: 判別可能ユニオン (discriminated union)
 * 例外を投げる代わりに「成功か失敗か」を型で表す。
 * `ok` を確認しない限り `value` に触れないため、エラー処理の書き忘れをコンパイル時に検出できる。
 */
export type Result<T, E> =
  | { readonly ok: true; readonly value: T }
  | { readonly ok: false; readonly error: E };

export const ok = <T>(value: T): Result<T, never> => ({ ok: true, value });
export const err = <E>(error: E): Result<never, E> => ({ ok: false, error });

/**
 * 特徴2: 網羅性チェック (exhaustiveness check)
 * switch で全ケースを処理していれば引数の型は `never` になる。
 * ユニオンに新しい種類を足して処理を書き忘れると、ここでコンパイルエラーになる。
 */
export function assertNever(x: never): never {
  throw new Error(`想定外の値です: ${JSON.stringify(x)}`);
}
