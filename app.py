from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_cors import CORS
import sqlite3
import bcrypt
import jwt
import datetime
import os
import threading

app = Flask(__name__)
CORS(app)

# Configurações
app.config['SECRET_KEY'] = 'fazenda-santo-antonio-2025-secret-key'
DATABASE = 'fazenda.db'

# Lock para thread safety
db_lock = threading.Lock()

def get_db_connection():
    """Conexão thread-safe com timeout"""
    conn = sqlite3.connect(DATABASE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializar banco de dados"""
    with db_lock:
        conn = get_db_connection()
        try:
            # Criar tabela de usuários
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Criar tabela de animais com campo proprietário
            conn.execute('''
                CREATE TABLE IF NOT EXISTS animals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    numero TEXT,
                    genero TEXT NOT NULL,
                    era_mes INTEGER,
                    era_ano INTEGER,
                    peso REAL,
                    status TEXT NOT NULL DEFAULT 'Vivo',
                    touro BOOLEAN DEFAULT 0,
                    observacao TEXT,
                    foto TEXT,
                    proprietario TEXT NOT NULL,
                    denominacao TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Verificar se usuário padrão existe
            user = conn.execute('SELECT * FROM users WHERE email = ?', ('felippe.lahr@gmail.com',)).fetchone()
            if not user:
                # Criar usuário padrão
                password_hash = bcrypt.hashpw('123456'.encode('utf-8'), bcrypt.gensalt())
                conn.execute(
                    'INSERT INTO users (name, email, password) VALUES (?, ?, ?)',
                    ('Felippe Lahr', 'felippe.lahr@gmail.com', password_hash)
                )
            
            conn.commit()
        finally:
            conn.close()

def calcular_denominacao(genero, era_mes, era_ano, numero, touro):
    """Calcular denominação baseada nas regras CORRETAS estabelecidas pelo usuário"""
    
    # PRIORIDADE 1: Touro (máxima prioridade)
    if touro:
        return 'Touro'
    
    # PRIORIDADE 2: Animais com número e SEM idade preenchida
    if numero and numero.strip():
        # Se tem número mas não tem idade, é Vaca/Boi
        if not era_mes or not era_ano:
            if genero == 'Fêmea':
                return 'Vaca'
            elif genero == 'Macho':
                return 'Boi'
        # Se tem número E tem idade, ainda é Vaca/Boi (número tem prioridade)
        else:
            if genero == 'Fêmea':
                return 'Vaca'
            elif genero == 'Macho':
                return 'Boi'
    
    # PRIORIDADE 3: Animais SEM número (baseado na idade)
    # Calcular idade em meses apenas se ambos os campos estão preenchidos
    idade_meses = None
    if era_mes and era_ano:
        hoje = datetime.date.today()
        idade_meses = (hoje.year - era_ano) * 12 + (hoje.month - era_mes)
    
    # Regras para Fêmeas SEM NÚMERO
    if genero == 'Fêmea':
        if idade_meses is not None:
            if idade_meses < 14:
                return 'Bezerro Fêmea'
            elif idade_meses <= 24:
                return 'Novilha'
            else:  # > 24 meses
                return 'Vaca sem número'
        else:
            # Sem idade definida e sem número, assume bezerro
            return 'Bezerro Fêmea'
    
    # Regras para Machos SEM NÚMERO (não touro)
    elif genero == 'Macho':
        if idade_meses is not None:
            if idade_meses < 14:
                return 'Bezerro Macho'
            elif idade_meses <= 24:
                return 'Garrote'
            else:  # > 24 meses
                return 'Boi sem número'
        else:
            # Sem idade definida e sem número, assume bezerro
            return 'Bezerro Macho'
    
    # Fallback (não deveria chegar aqui)
    return 'Indefinido'

# Rotas principais
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/cadastro')
def cadastro():
    return render_template('cadastro.html')

@app.route('/lista')
def lista():
    return render_template('lista.html')

# APIs
@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({'success': False, 'message': 'Email e senha são obrigatórios'})
        
        with db_lock:
            conn = get_db_connection()
            try:
                user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
                
                if user:
                    # Converter password do banco para bytes se necessário
                    stored_password = user['password']
                    if isinstance(stored_password, str):
                        stored_password = stored_password.encode('utf-8')
                    
                    if bcrypt.checkpw(password.encode('utf-8'), stored_password):
                        # Gerar token JWT
                        token = jwt.encode({
                            'user_id': user['id'],
                            'email': user['email'],
                            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
                        }, app.config['SECRET_KEY'], algorithm='HS256')
                        
                        return jsonify({
                            'success': True,
                            'token': token,
                            'user': {
                                'id': user['id'],
                                'name': user['name'],
                                'email': user['email']
                            }
                        })
                    else:
                        return jsonify({'success': False, 'message': 'Credenciais inválidas'})
                else:
                    return jsonify({'success': False, 'message': 'Credenciais inválidas'})
            finally:
                conn.close()
                
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})

@app.route('/api/dashboard/stats', methods=['GET'])
def api_dashboard_stats():
    try:
        with db_lock:
            conn = get_db_connection()
            try:
                # Buscar todos os animais
                animals = conn.execute("SELECT * FROM animals WHERE status = 'Vivo'").fetchall()
                
                # Converter para lista de dicionários
                animals = [dict(animal) for animal in animals]
                
                # Calcular estatísticas
                stats = {
                    'total': len(animals),
                    'bezerro_femea': 0,
                    'bezerro_macho': 0,
                    'novilha': 0,
                    'garrote': 0,
                    'vaca': 0,
                    'boi': 0,
                    'vaca_sem_numero': 0,
                    'boi_sem_numero': 0,
                    'touro': 0,
                    'vacas_total': 0,
                    'vacas_sem_numero': 0,
                    'bois_total': 0,
                    'bois_sem_numero': 0
                }
                
                for animal in animals:
                    denominacao = animal['denominacao']
                    
                    if denominacao == 'Bezerro Fêmea':
                        stats['bezerro_femea'] += 1
                    elif denominacao == 'Bezerro Macho':
                        stats['bezerro_macho'] += 1
                    elif denominacao == 'Novilha':
                        stats['novilha'] += 1
                    elif denominacao == 'Garrote':
                        stats['garrote'] += 1
                    elif denominacao == 'Vaca':
                        stats['vaca'] += 1
                        stats['vacas_total'] += 1
                    elif denominacao == 'Boi':
                        stats['boi'] += 1
                        stats['bois_total'] += 1
                    elif denominacao == 'Vaca sem número':
                        stats['vaca_sem_numero'] += 1
                        stats['vacas_total'] += 1
                        stats['vacas_sem_numero'] += 1
                    elif denominacao == 'Boi sem número':
                        stats['boi_sem_numero'] += 1
                        stats['bois_total'] += 1
                        stats['bois_sem_numero'] += 1
                    elif denominacao == 'Touro':
                        stats['touro'] += 1
                
                return jsonify(stats)
            finally:
                conn.close()
                
    except Exception as e:
        return jsonify({'error': f'Erro ao buscar estatísticas: {str(e)}'})

@app.route('/api/animals', methods=['GET'])
def api_get_animals():
    try:
        # Parâmetros de filtro
        search = request.args.get('search', '')
        denominacao_filter = request.args.get('denominacao', '')
        status_filter = request.args.get('status', '')
        proprietario_filter = request.args.get('proprietario', '')
        era_de_mes = request.args.get('era_de_mes', '')
        era_de_ano = request.args.get('era_de_ano', '')
        era_ate_mes = request.args.get('era_ate_mes', '')
        era_ate_ano = request.args.get('era_ate_ano', '')
        
        with db_lock:
            conn = get_db_connection()
            try:
                query = 'SELECT * FROM animals WHERE 1=1'
                params = []
                
                # Filtro de busca geral
                if search:
                    query += ' AND (numero LIKE ? OR observacao LIKE ?)'
                    params.extend([f'%{search}%', f'%{search}%'])
                
                # Filtro por denominação
                if denominacao_filter:
                    query += ' AND denominacao = ?'
                    params.append(denominacao_filter)
                
                # Filtro por status
                if status_filter:
                    query += ' AND status = ?'
                    params.append(status_filter)
                
                # Filtro por proprietário
                if proprietario_filter:
                    query += ' AND proprietario = ?'
                    params.append(proprietario_filter)
                
                # Filtro por era (período)
                if era_de_mes and era_de_ano:
                    query += ' AND (era_ano > ? OR (era_ano = ? AND era_mes >= ?))'
                    params.extend([int(era_de_ano), int(era_de_ano), int(era_de_mes)])
                
                if era_ate_mes and era_ate_ano:
                    query += ' AND (era_ano < ? OR (era_ano = ? AND era_mes <= ?))'
                    params.extend([int(era_ate_ano), int(era_ate_ano), int(era_ate_mes)])
                
                query += ' ORDER BY id DESC'
                
                animals = conn.execute(query, params).fetchall()
                
                # Converter para lista de dicionários
                animals_list = []
                for animal in animals:
                    animal_dict = dict(animal)
                    animals_list.append(animal_dict)
                
                return jsonify(animals_list)
            finally:
                conn.close()
                
    except Exception as e:
        return jsonify({'error': f'Erro ao buscar animais: {str(e)}'})

@app.route('/api/animals', methods=['POST'])
def api_create_animal():
    try:
        data = request.get_json()
        
        # Validações obrigatórias
        if not data.get('genero'):
            return jsonify({'success': False, 'message': 'Gênero é obrigatório'})
        
        if not data.get('proprietario'):
            return jsonify({'success': False, 'message': 'Proprietário é obrigatório'})
        
        if not data.get('status'):
            return jsonify({'success': False, 'message': 'Status é obrigatório'})
        
        # Extrair dados
        numero = data.get('numero', '').strip()
        genero = data.get('genero')
        era_mes = data.get('era_mes')
        era_ano = data.get('era_ano')
        peso = data.get('peso')
        status = data.get('status')
        touro = data.get('touro', False)
        observacao = data.get('observacao', '')
        proprietario = data.get('proprietario')
        
        # Converter era para inteiros se preenchidos
        if era_mes:
            era_mes = int(era_mes)
        if era_ano:
            era_ano = int(era_ano)
        
        # Calcular denominação
        denominacao = calcular_denominacao(genero, era_mes, era_ano, numero, touro)
        
        with db_lock:
            conn = get_db_connection()
            try:
                conn.execute('''
                    INSERT INTO animals (numero, genero, era_mes, era_ano, peso, status, touro, observacao, proprietario, denominacao)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (numero, genero, era_mes, era_ano, peso, status, touro, observacao, proprietario, denominacao))
                
                conn.commit()
                
                return jsonify({
                    'success': True,
                    'message': 'Animal cadastrado com sucesso',
                    'denominacao': denominacao
                })
            finally:
                conn.close()
                
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao cadastrar animal: {str(e)}'})

@app.route('/api/animals/<int:animal_id>', methods=['PUT'])
def api_update_animal(animal_id):
    try:
        data = request.get_json()
        
        with db_lock:
            conn = get_db_connection()
            try:
                # Buscar animal atual
                animal = conn.execute('SELECT * FROM animals WHERE id = ?', (animal_id,)).fetchone()
                if not animal:
                    return jsonify({'success': False, 'message': 'Animal não encontrado'})
                
                # Campos que podem ser editados
                genero = data.get('genero', animal['genero'])
                era_mes = data.get('era_mes', animal['era_mes'])
                era_ano = data.get('era_ano', animal['era_ano'])
                peso = data.get('peso', animal['peso'])
                status = data.get('status', animal['status'])
                touro = data.get('touro', animal['touro'])
                observacao = data.get('observacao', animal['observacao'])
                
                # Campos NÃO editáveis (mantém os valores originais)
                numero = animal['numero']  # Não pode ser alterado
                proprietario = animal['proprietario']  # Não pode ser alterado
                
                # Recalcular denominação
                denominacao = calcular_denominacao(genero, era_mes, era_ano, numero, touro)
                
                conn.execute('''
                    UPDATE animals 
                    SET genero=?, era_mes=?, era_ano=?, peso=?, status=?, touro=?, observacao=?, denominacao=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                ''', (genero, era_mes, era_ano, peso, status, touro, observacao, denominacao, animal_id))
                
                conn.commit()
                
                return jsonify({
                    'success': True,
                    'message': 'Animal atualizado com sucesso',
                    'denominacao': denominacao
                })
            finally:
                conn.close()
                
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao atualizar animal: {str(e)}'})

@app.route('/api/animals/<int:animal_id>', methods=['DELETE'])
def api_delete_animal(animal_id):
    try:
        with db_lock:
            conn = get_db_connection()
            try:
                # Verificar se animal existe
                animal = conn.execute('SELECT * FROM animals WHERE id = ?', (animal_id,)).fetchone()
                if not animal:
                    return jsonify({'success': False, 'message': 'Animal não encontrado'})
                
                # Excluir animal
                conn.execute('DELETE FROM animals WHERE id = ?', (animal_id,))
                conn.commit()
                
                return jsonify({'success': True, 'message': 'Animal excluído com sucesso'})
            finally:
                conn.close()
                
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao excluir animal: {str(e)}'})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)

