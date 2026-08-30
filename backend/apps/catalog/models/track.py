from django.db import models


class Track(models.Model):
    """Trilha com arco narrativo.

    `student_role` é texto fixo: o mesmo papel vale em todos os cenários desta trilha,
    e não é preenchido a partir do perfil profissional do aluno.
    """

    slug = models.SlugField(max_length=80, unique=True)
    title = models.CharField(max_length=120)
    order = models.PositiveSmallIntegerField(unique=True)
    student_role = models.TextField()

    class Meta:
        ordering = ["order"]

    def __str__(self) -> str:
        return self.title
