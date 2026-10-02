"""Recognize bounded, read-only PowerShell queries without evaluating code."""
import re
from pathlib import Path

PROPERTIES={'name','fullname','length','extension','lastwritetime','creationtime','attributes','psiscontainer'}

def tokenize(command):
    if len(command)>12000 or any(char in command for char in '`\r\n\x00&<>@#()[]'):raise ValueError('Unsupported shell syntax')
    tokens=[];position=0
    while position<len(command):
        char=command[position]
        if char.isspace():position+=1;continue
        if char in ';|{},':tokens.append((char,char));position+=1;continue
        if char in "'\"":
            quote=char;start=position+1;position=start
            while position<len(command) and command[position]!=quote:position+=1
            if position==len(command):raise ValueError('Unclosed string')
            value=command[start:position]
            if '$' in value or '\x00' in value:raise ValueError('Interpolation is not allowed')
            tokens.append(('string',value));position+=1;continue
        start=position
        while position<len(command) and not command[position].isspace() and command[position] not in ';|{},\'"':position+=1
        value=command[start:position]
        if not value:raise ValueError('Bad token')
        tokens.append(('word',value))
    return tokens

class QueryParser:
    def __init__(self,command,guard):self.tokens=tokenize(command);self.position=0;self.guard=guard;self.file_queries=0
    def peek(self):return self.tokens[self.position] if self.position<len(self.tokens) else None
    def take(self):
        token=self.peek()
        if token is None:raise ValueError('Missing argument')
        self.position+=1;return token
    def value(self):
        kind,value=self.take()
        if kind not in ('word','string') or (kind=='word' and ('$' in value or value.startswith('-'))):raise ValueError('Expected literal value')
        return value
    def number(self,maximum=5000):
        value=self.value()
        if not value.isascii() or not value.isdigit() or int(value)>maximum:raise ValueError('Invalid bound')
    def patterns(self):
        for _ in range(16):
            value=self.value()
            if not value or '$' in value or any(char in value for char in '\\/:'):raise ValueError('Only filename patterns are allowed')
            if not self.peek() or self.peek()[0]!=',':return
            self.take()
        raise ValueError('Too many patterns')
    def source(self):
        kind,verb=self.take();verb=verb.lower()
        if kind=='string':
            if self.peek() and self.peek()[0] not in (';',):raise ValueError('Literal cannot invoke a command')
            return 'literal'
        if kind!='word' or verb not in ('get-childitem','dir','get-content','test-path','get-filehash','get-location','pwd','write-output','echo'):
            raise ValueError('Not a read-only command')
        paths=[];literal=False
        while self.peek() and self.peek()[0] not in ('|',';'):
            token=self.peek();value=token[1];lower=value.lower()
            if token[0]=='word' and lower.startswith('-'):
                self.take()
                if lower in ('-literalpath','-path') and verb not in ('get-location','pwd','write-output','echo'):
                    if paths:raise ValueError('Only one source path')
                    literal=lower=='-literalpath';paths.append(self.value())
                elif verb in ('get-childitem','dir') and lower in ('-recurse','-file','-directory','-force','-name'):pass
                elif verb in ('get-childitem','dir') and lower in ('-include','-exclude','-filter'):self.patterns()
                elif lower=='-erroraction' and verb in ('get-childitem','dir','get-content','test-path','get-filehash'):
                    if self.value().lower() not in ('silentlycontinue','stop','continue'):raise ValueError('Unsupported error action')
                elif verb=='get-content' and lower in ('-totalcount','-tail'):self.number()
                elif verb=='get-childitem' and lower=='-depth':self.number(10)
                elif verb=='get-filehash' and lower=='-algorithm':
                    if self.value().upper() not in ('SHA256','SHA384','SHA512'):raise ValueError('Unsupported hash')
                else:raise ValueError('Unknown command switch')
            else:
                value=self.value()
                if verb in ('write-output','echo'):continue
                if verb in ('get-location','pwd') or paths:raise ValueError('Unexpected source argument')
                paths.append(value)
        if verb in ('get-location','pwd','write-output','echo'):return 'literal'
        directory=verb in ('get-childitem','dir')
        if not paths and not directory:raise ValueError('An explicit file is required')
        for path in paths or ['.']:
            drive=re.match(r'^[A-Za-z]:[\\/]',path)
            if ':' in (path[2:] if drive else path):raise ValueError('Providers and alternate data streams are not file queries')
            if '*' in path or '?' in path:
                if not directory or literal:raise ValueError('File reads and literal paths cannot expand globs')
                parent=str(Path(path).parent)
                if '*' in parent or '?' in parent:raise ValueError('Only a filename glob is allowed')
                self.guard(parent,directory=True)
            else:self.guard(path,directory=directory)
        self.file_queries+=1
        return 'files' if directory else 'content'
    def selector(self):
        verb=self.take()
        if verb[0]!='word' or verb[1].lower() not in ('select-object','select'):raise ValueError('Unknown pipeline stage')
        found=False
        while self.peek() and self.peek()[0] not in ('|',';'):
            token=self.take();lower=token[1].lower()
            if token[0]!='word':raise ValueError('Unknown selection')
            if lower in ('-first','-last','-skip'):self.number();found=True
            elif lower in ('-expandproperty','-property'):
                if self.value().lower() not in PROPERTIES:raise ValueError('Only metadata properties may be selected')
                found=True
            elif lower in PROPERTIES:found=True
            else:raise ValueError('Unsupported selection')
        if not found:raise ValueError('An explicit selection is required')
    def where(self):
        verb=self.take()
        if verb[0]!='word' or verb[1].lower() not in ('where-object','where'):raise ValueError('Unknown filter')
        if self.take()[0]!='{':raise ValueError('A filter expression is required')
        for _ in range(12):
            token=self.take();match=re.fullmatch(r'\$_\.([A-Za-z]+)',token[1])
            if token[0]!='word' or not match or match[1].lower() not in PROPERTIES:raise ValueError('Only metadata may be compared')
            operator=self.take()
            if operator[0]!='word' or operator[1].lower() not in ('-like','-notlike','-eq','-ne'):raise ValueError('Unsupported comparison')
            value=self.take()
            if value[0] not in ('word','string') or '$' in value[1] or value[1].startswith('-'):raise ValueError('A literal comparison is required')
            token=self.take()
            if token[0]=='}':return
            if token[0]!='word' or token[1].lower() not in ('-and','-or'):raise ValueError('Unsupported conjunction')
        raise ValueError('Filter is too large')
    def parse(self):
        if not self.tokens:return False
        for _ in range(8):
            kind=self.source()
            for _ in range(6):
                if not self.peek() or self.peek()[0]!='|':break
                self.take();token=self.peek()
                if not token:raise ValueError('Empty pipeline')
                if token[1].lower() in ('where-object','where') and kind=='files':self.where()
                elif token[0]=='word' and token[1].lower() in ('select-object','select'):self.selector()
                else:raise ValueError('Unknown pipeline')
            if not self.peek():return True
            if self.take()[0]!=';' or not self.peek():raise ValueError('Unsupported statement')
        raise ValueError('Too many statements')

def is_routine_query(command,guard):
    try:return QueryParser(command,guard).parse()
    except (ValueError,OSError,TypeError):return False
