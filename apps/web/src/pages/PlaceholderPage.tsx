type PlaceholderPageProps = {
  title: string
  story: string
}

export function PlaceholderPage({ title, story }: PlaceholderPageProps) {
  return (
    <section className="page">
      <h1>{title}</h1>
      <p>Coming in story {story}.</p>
    </section>
  )
}
