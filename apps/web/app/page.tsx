import Link from "next/link";

export default function Home() {
  return (
    <section className="hero">
      <p className="eyebrow">Platform foundation</p>
      <h1>MimicMotion web platform</h1>
      <p>The secure account and media-upload foundation is being prepared. Camera generation is not enabled yet.</p>
      <div className="actions">
        <Link className="button" href="/register">Create account</Link>
        <Link className="button secondary" href="/login">Sign in</Link>
      </div>
    </section>
  );
}
