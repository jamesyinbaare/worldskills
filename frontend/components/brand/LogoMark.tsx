import Image from "next/image";

type LogoMarkProps = {
  className?: string;
  priority?: boolean;
};

export function CrestLogo({ className, priority }: LogoMarkProps) {
  return (
    <Image
      src="/logo-crest-only.png"
      alt="CTVET — Commission for Technical and Vocational Education and Training"
      width={160}
      height={160}
      className={className}
      priority={priority}
    />
  );
}

export function WorldSkillsLogo({ className, priority }: LogoMarkProps) {
  return (
    <Image
      src="/world-skills-logo.jpg"
      alt="WorldSkills Ghana"
      width={320}
      height={200}
      className={className}
      priority={priority}
    />
  );
}
