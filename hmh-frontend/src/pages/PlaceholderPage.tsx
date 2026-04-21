interface PlaceholderPageProps {
  title: string;
  description: string;
  icon: React.ElementType;
}

export function PlaceholderPage({ title, description, icon: Icon }: PlaceholderPageProps) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] animate-fade-in">
      <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-primary/10 mb-5">
        <Icon className="w-7 h-7 text-primary" />
      </div>
      <h2 className="text-xl font-semibold">{title}</h2>
      <p className="text-sm text-muted-foreground mt-2 text-center max-w-xs">{description}</p>
      <p className="mt-4 text-xs text-muted-foreground bg-muted px-3 py-1.5 rounded-full">Coming in next build phase</p>
    </div>
  );
}
