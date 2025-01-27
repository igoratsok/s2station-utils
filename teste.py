import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def enviar_email_teste(smtp_server, smtp_port, login, senha, destinatario):
    try:
        # Configurar a mensagem
        msg = MIMEMultipart()
        msg['From'] = login
        msg['To'] = destinatario
        msg['Subject'] = 'Teste de SMTP'
        body = 'Este é um e-mail de teste enviado pelo script Python.'
        msg.attach(MIMEText(body, 'plain'))

        # Conectar ao servidor SMTP
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # Iniciar TLS para segurança
        server.login(login, senha)  # Fazer login no servidor
        text = msg.as_string()
        server.sendmail("avisa.tesouro@tesouro.gov.br", destinatario, text)  # Enviar e-mail
        server.quit()  # Fechar a conexão com o servidor

        print("E-mail enviado com sucesso!")
    except Exception as e:
        print(f"Falha ao enviar e-mail: {e}")

# Configurações do servidor SMTP
smtp_server = 'smtp-lob.office365.com'
smtp_port = 587
login = 'avisa.tesouro_smtp@tesouro.gov.br'
senha = '123@abcd'
destinatario = 'igor.a.costa@tesouro.gov.br'

# Enviar e-mail de teste
enviar_email_teste(smtp_server, smtp_port, login, senha, destinatario)